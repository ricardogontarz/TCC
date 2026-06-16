"""
M3 — Pipeline RAG (extração).
=============================
Junta as peças: OCR (M1) -> busca de exemplos (M2) -> prompt few-shot ->
LLM (Gemini) -> validação Pydantic. Cumpre o Objetivo 1 (ponta a ponta) e dá
suporte ao Objetivo 4 via a flag `use_rag` (liga/desliga a recuperação).

Dois freios anti-alucinação convivem aqui:
  1. O prompt instrui explicitamente "ausente = null, nunca invente".
  2. A saída é validada contra o schema Pydantic; se inválida, 1 retry anexando
     o erro ao prompt.
"""

import json
import os
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple, Type, Union

import google.generativeai as genai
import ollama
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from nucleo.banco_vetorial import BancoVetorial
from nucleo.config import MODELO_LLM, MODELO_OLLAMA, OLLAMA_HOST, PROVEDOR_LLM
from nucleo.ocr import ocr_extrair_texto
from nucleo.schema import ReciboSROIE

# Carrega o .env (ex.: GOOGLE_API_KEY) assim que o módulo é importado.
load_dotenv()


# Instruções padrão: recibos escaneados (o domínio do gabarito SROIE). São as
# MESMAS usadas pela avaliação — app e experimento compartilham o prompt.
INSTRUCOES = """You are a data extractor for scanned retail receipts.
Extract ONLY information present in the provided OCR text. If a field is not
in the text, return null — NEVER invent, deduce or complete values.
The OCR text may contain recognition noise; extract the value as printed,
fixing only obvious character-level OCR errors. "total" is the final amount
paid, as a number (no currency symbol). "date" is the receipt date as printed.
Answer ONLY with a valid JSON that follows this schema:
{schema}
"""


@dataclass
class ResultadoExtracao:
    """Resultado instrumentado da extração — usado pelo harness de avaliação (M5)
    para medir a taxa de JSON válido já na 1ª tentativa, sem alterar o caminho
    de produção."""
    texto_ocr: str
    nota: Optional[BaseModel]    # ReciboSROIE (fixo) ou modelo dinâmico (app)
    valido_primeira: bool        # True se a 1ª chamada ao LLM já validou
    n_tentativas: int            # 1 ou 2
    erro: Optional[str]          # mensagem se falhou nas 2 tentativas
    # --- Instrumentação (banco de resultados + métricas de tempo/custo) ---
    json_bruto: Optional[str] = None      # última saída crua do LLM (mesmo inválida)
    k_exemplos: int = 0                   # nº de exemplos recuperados (RAG)
    duracao_ocr_s: Optional[float] = None
    duracao_llm_s: Optional[float] = None  # soma das chamadas (inclui retry)
    duracao_total_s: Optional[float] = None
    tokens_entrada: Optional[int] = None   # soma das chamadas; None se o provedor não informar
    tokens_saida: Optional[int] = None
    registro_id: Optional[str] = None      # id no banco de resultados (preenchido por quem registra)


@dataclass
class RespostaLLM:
    """Saída crua de uma chamada ao LLM + contagem de tokens (quando o provedor
    informa). Interno ao pipeline."""
    texto: str
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None


def montar_prompt(
    texto_ocr: str,
    exemplos: List[dict],
    schema_json: str,
    instrucoes: Optional[str] = None,
) -> str:
    """Monta o prompt few-shot: instruções + schema + exemplos recuperados + OCR.

    `instrucoes`: texto de sistema com placeholder {schema}. Default são as
    instruções de recibos (INSTRUCOES) — as mesmas da avaliação SROIE."""
    partes = [(instrucoes or INSTRUCOES).format(schema=schema_json)]
    if exemplos:
        partes.append("\nExemplos de extrações já validadas por humanos:")
        for ex in exemplos:
            partes.append(f"\nTEXTO OCR:\n{ex['ocr']}\n\nJSON:\n{ex['json']}")
    partes.append(
        f"\nAgora extraia deste documento.\nTEXTO OCR:\n{texto_ocr}\n\nJSON:"
    )
    return "\n".join(partes)


def gerar_json(
    prompt: str, provedor: Optional[str] = None, modelo: Optional[str] = None
) -> RespostaLLM:
    """Gera o JSON chamando o LLM do provedor escolhido.

    provedor/modelo são opcionais: quando None, caem nos valores de config.py
    (PROVEDOR_LLM, MODELO_OLLAMA/MODELO_LLM). Isso preserva o comportamento da
    CLI e da avaliação (M5) e ainda permite ao frontend escolher em tempo de
    execução, sem precisar editar o config.
    """
    provedor = provedor or PROVEDOR_LLM
    if provedor == "ollama":
        return _gerar_json_ollama(prompt, modelo or MODELO_OLLAMA)
    return _gerar_json_gemini(prompt, modelo or MODELO_LLM)


def _gerar_json_gemini(prompt: str, modelo: str = MODELO_LLM) -> RespostaLLM:
    """Chama o Gemini pedindo explicitamente uma resposta em JSON."""
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    cliente = genai.GenerativeModel(modelo)
    resposta = cliente.generate_content(
        prompt, generation_config={"response_mime_type": "application/json"}
    )
    uso = getattr(resposta, "usage_metadata", None)
    return RespostaLLM(
        texto=resposta.text,
        tokens_entrada=getattr(uso, "prompt_token_count", None),
        tokens_saida=getattr(uso, "candidates_token_count", None),
    )


def _gerar_json_ollama(prompt: str, modelo: str = MODELO_OLLAMA) -> RespostaLLM:
    """Chama um LLM LOCAL via Ollama. format='json' força saída JSON válida —
    grátis, sem cota nem rate-limit, roda offline na máquina.

    think=False desliga o "raciocínio" dos modelos híbridos/reasoning
    (qwen3, gemma4, deepseek-r1). Sem isso o traço de raciocínio vaza no
    `content` e o JSON sai inválido (o format='json' sozinho não contém).
    Para esta tarefa — copiar campos do OCR — não se quer raciocínio: quer-se
    JSON limpo. Modelos que não suportam thinking (ex.: llama3.1) recusam o
    parâmetro, daí o fallback que repete a chamada sem ele."""
    cliente = ollama.Client(host=OLLAMA_HOST)
    comum = dict(
        model=modelo,
        messages=[{"role": "user", "content": prompt}],
        format="json",
    )
    try:
        resposta = cliente.chat(think=False, **comum)
    except Exception:
        resposta = cliente.chat(**comum)
    return RespostaLLM(
        texto=resposta["message"]["content"],
        tokens_entrada=resposta.get("prompt_eval_count"),
        tokens_saida=resposta.get("eval_count"),
    )


def extrair(
    caminho_imagem: str,
    banco: BancoVetorial,
    use_rag: bool = True,
    retornar_metadados: bool = False,
    provedor: Optional[str] = None,
    modelo: Optional[str] = None,
    modelo_schema: Type[BaseModel] = ReciboSROIE,
    excluir_self: bool = False,
    texto_ocr: Optional[str] = None,
    idioma_ocr: Optional[str] = None,
    instrucoes: Optional[str] = None,
) -> Union[Tuple[str, BaseModel], ResultadoExtracao]:
    """Extrai os dados estruturados de uma imagem de documento.

    - use_rag: liga/desliga a recuperação de exemplos (baseline do Objetivo 4).
    - retornar_metadados=False (default): mantém o contrato simples
      `(texto_ocr, modelo)` .
    - retornar_metadados=True: devolve um ResultadoExtracao rico, com a
      informação de validade da 1ª tentativa (consumido pela avaliação).
    - provedor/modelo: opcionais; quando None caem no config. O frontend usa
      isso para deixar o usuário escolher o LLM em tempo de execução.
    - modelo_schema: classe Pydantic que define os campos a extrair. Default é
      o schema FIXO do gabarito (ReciboSROIE), usado pela avaliação. App e CLI
      passam um schema DINÂMICO (campos configuráveis) — daí o prompt e a
      validação se adaptam aos campos escolhidos, sem duplicar este código.
    - excluir_self: leave-one-out. Quando True, a busca RAG ignora o exemplo
      cujo OCR é igual ao desta imagem — usado ao avaliar sobre os APROVADOS
      (a nota não pode se recuperar a si mesma e inflar a métrica).
    - texto_ocr: quando fornecido, PULA o OCR e usa este texto. O harness SROIE
      usa isso para garantir o pareamento estrito: baseline e RAG recebem
      EXATAMENTE o mesmo texto de entrada (OCR feito uma única vez e cacheado).
    - idioma_ocr: língua do Tesseract (None = config.IDIOMA_OCR; SROIE usa "eng").

    A validação Pydantic + 1 retry de correção é o segundo freio anti-alucinação.
    """
    inicio_total = time.perf_counter()
    duracao_ocr: Optional[float] = None
    if texto_ocr is None:
        inicio_ocr = time.perf_counter()
        texto_ocr = ocr_extrair_texto(caminho_imagem, idioma=idioma_ocr)
        duracao_ocr = time.perf_counter() - inicio_ocr
    if use_rag:
        exemplos = banco.buscar(
            texto_ocr, excluir_texto=texto_ocr if excluir_self else None
        )
    else:
        exemplos = []
    schema_json = json.dumps(
        modelo_schema.model_json_schema(), ensure_ascii=False, indent=2
    )
    prompt = montar_prompt(texto_ocr, exemplos, schema_json, instrucoes=instrucoes)

    ultimo_erro: Optional[str] = None
    bruto: Optional[str] = None
    duracao_llm = 0.0
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None

    def _somar_tokens(resposta: RespostaLLM) -> None:
        nonlocal tokens_entrada, tokens_saida
        if resposta.tokens_entrada is not None:
            tokens_entrada = (tokens_entrada or 0) + resposta.tokens_entrada
        if resposta.tokens_saida is not None:
            tokens_saida = (tokens_saida or 0) + resposta.tokens_saida

    def _montar_resultado(nota, valido_primeira, n_tentativas, erro) -> ResultadoExtracao:
        return ResultadoExtracao(
            texto_ocr=texto_ocr,
            nota=nota,
            valido_primeira=valido_primeira,
            n_tentativas=n_tentativas,
            erro=erro,
            json_bruto=bruto,
            k_exemplos=len(exemplos),
            duracao_ocr_s=duracao_ocr,
            duracao_llm_s=duracao_llm,
            duracao_total_s=time.perf_counter() - inicio_total,
            tokens_entrada=tokens_entrada,
            tokens_saida=tokens_saida,
        )

    for tentativa in range(1, 3):  # 1 tentativa + 1 retry
        inicio_llm = time.perf_counter()
        resposta = gerar_json(prompt, provedor, modelo)
        duracao_llm += time.perf_counter() - inicio_llm
        bruto = resposta.texto
        _somar_tokens(resposta)
        try:
            nota = modelo_schema.model_validate_json(bruto)
            if retornar_metadados:
                return _montar_resultado(nota, tentativa == 1, tentativa, None)
            return texto_ocr, nota
        except ValidationError as erro:
            ultimo_erro = str(erro)
            prompt += (
                f"\n\nO JSON anterior era inválido:\n{erro}\n"
                "Corrija e responda APENAS com um JSON válido."
            )

    # Falhou nas duas tentativas.
    if retornar_metadados:
        return _montar_resultado(None, False, 2, ultimo_erro)
    raise RuntimeError("Não foi possível obter um JSON válido após 2 tentativas.")
