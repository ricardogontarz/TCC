"""
M3/M4 — Serviço de domínio (agnóstico de framework).
=====================================================
Concentra as operações de negócio do frontend, SEM nenhuma dependência do
Streamlit (`st.*`): assim a regra fica testável de forma isolada e poderia ser
reusada pelo CLI/terminal ou por um harness.

- `executar_extracao_pareada` — orquestra OCR + LLM a partir dos bytes
  enviados, nas DUAS condições (sem RAG e com RAG) sobre o mesmo texto OCR,
  repassando o schema DINÂMICO (campos configuráveis) ao pipeline.
- `_para_numero` / `montar_dados` — transformam o que o usuário digitou no
  formulário num dict pronto para o Pydantic (parsing puro).
- `validar_e_gravar` — a regra do M4: só dados válidos (Pydantic) entram na base.

Quem lê o `session_state`, exibe erros ou dá rerun é a camada de view/página;
aqui as exceções são propagadas de propósito.
"""

import os
import tempfile
import uuid
from typing import List, Optional, Type

from pydantic import BaseModel

from nucleo import campos as campos_mod
from nucleo import registro
from nucleo.banco_vetorial import BancoVetorial
from nucleo.config import DIR_APROVADAS
from nucleo.pipeline import extrair


def executar_extracao_pareada(
    conteudo_bytes: bytes,
    nome_arquivo: str,
    banco: BancoVetorial,
    provedor: str,
    modelo: str,
    modelo_schema: Type[BaseModel],
    versao_campos: Optional[int] = None,
    idioma_ocr: Optional[str] = None,
) -> dict:
    """Extração PAREADA: roda as DUAS condições (baseline sem RAG e com RAG)
    sobre o MESMO texto OCR e devolve {"sem_rag": ..., "com_rag": ...}.

    O OCR acontece UMA vez (na 1ª condição) e é injetado na 2ª via `texto_ocr` —
    o mesmo pareamento estrito do harness de avaliação, agora ao vivo na tela:
    o operador vê os dois resultados e aprova um deles (Objetivo 4 na prática).

    Grava os bytes num arquivo temporário (o pipeline/ocr.py trabalha com
    CAMINHO, não com bytes) e SEMPRE o remove no finally. Exceções (Ollama
    offline, chave Gemini ausente, etc.) sobem para a página tratar.

    CADA condição entra no banco de RESULTADOS como 'pendente'
    (`resultado.registro_id`); a decisão do operador atualiza os status depois
    (a escolhida vira 'aprovado'; a outra, 'rejeitado')."""
    sufixo = os.path.splitext(nome_arquivo)[1] or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=sufixo) as tmp:
        tmp.write(conteudo_bytes)
        caminho_tmp = tmp.name
    try:
        comum = dict(
            retornar_metadados=True,
            provedor=provedor,
            modelo=modelo,
            modelo_schema=modelo_schema,
        )
        sem_rag = extrair(
            caminho_tmp, banco, use_rag=False, idioma_ocr=idioma_ocr, **comum
        )
        com_rag = extrair(
            caminho_tmp, banco, use_rag=True, texto_ocr=sem_rag.texto_ocr, **comum
        )
    finally:
        os.unlink(caminho_tmp)

    resultados = {"sem_rag": sem_rag, "com_rag": com_rag}
    for condicao, resultado in resultados.items():
        resultado.registro_id = registro.registrar_resultado(
            resultado,
            documento_origem=nome_arquivo,
            use_rag=(condicao == "com_rag"),
            provedor=provedor,
            modelo=modelo,
            experimento="app",
            versao_campos=versao_campos,
        )
    return resultados


def descartar(registro_id: Optional[str]) -> None:
    """Marca a extração como REJEITADA no banco de resultados (o descarte
    deixava de existir antes — agora fica rastreável)."""
    if registro_id:
        registro.atualizar_status(registro_id, "rejeitado")


def _para_numero(texto: str):
    """Converte o que o usuário digitou num número. Aceita 'R$ 1.234,56' (pt-BR)
    e '1234.56'. Se não der, devolve o texto original — o Pydantic recusa e o
    erro aparece no formulário (em vez de gravar lixo)."""
    t = str(texto).replace("R$", "").replace(" ", "")
    if "," in t:  # formato pt-BR: '.' é milhar, ',' é decimal
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return texto


def montar_dados(cfg: dict, valores_campos: dict, itens_edit: Optional[List[dict]]) -> dict:
    """Transforma os valores crus do formulário (strings) no dict que o schema
    dinâmico espera. Puro: não toca em session_state nem em Streamlit.

    - campo vazio -> None (campo ausente = null, nunca inventado);
    - campo do tipo 'numero' -> convertido com `_para_numero`;
    - itens: ignora linhas totalmente vazias; converte qtd/valor para número."""
    dados = {}
    for campo in cfg["campos"]:
        bruto = (valores_campos.get(campo["chave"]) or "").strip()
        if bruto == "":
            dados[campo["chave"]] = None
        elif campo["tipo"] == "numero":
            dados[campo["chave"]] = _para_numero(bruto)
        else:
            dados[campo["chave"]] = bruto

    if cfg.get("incluir_itens", True):
        campos_item = cfg.get("campos_item", [])
        itens = []
        for linha in (itens_edit or []):
            # Lê cada coluna configurada do item (string crua).
            brutos = {c["chave"]: (linha.get(c["chave"]) or "").strip() for c in campos_item}
            if not any(brutos.values()):
                continue  # ignora linhas totalmente vazias
            item = {}
            for c in campos_item:
                v = brutos[c["chave"]]
                if v == "":
                    item[c["chave"]] = None
                elif c["tipo"] == "numero":
                    item[c["chave"]] = _para_numero(v)
                else:
                    item[c["chave"]] = v
            itens.append(item)
        dados["itens"] = itens

    return dados


def persistir_aprovada(cfg: dict, imagem_bytes: Optional[bytes], nota_json: str) -> None:
    """Salva a nota aprovada como par <id>.png + <id>.json numa subpasta por
    VERSÃO dos campos (dados/aprovadas/v<n>/), no mesmo layout do dataset.
    Assim os aprovados de cada versão de campos ficam separados e a avaliação
    (M5, --aprovadas) pode usá-los como gabarito por versão. Sem bytes de
    imagem, salva só o JSON."""
    pasta = DIR_APROVADAS / f"v{campos_mod.versao_dos_campos(cfg)}"
    pasta.mkdir(parents=True, exist_ok=True)
    stem = f"aprovada_{uuid.uuid4().hex[:12]}"
    (pasta / f"{stem}.json").write_text(nota_json, encoding="utf-8")
    if imagem_bytes:
        (pasta / f"{stem}.png").write_bytes(imagem_bytes)


def validar_e_gravar(
    banco: BancoVetorial,
    modelo_schema: Type[BaseModel],
    texto_ocr: str,
    dados: dict,
    cfg: dict,
    imagem_bytes: Optional[bytes] = None,
    registro_id: Optional[str] = None,
) -> None:
    """Regra do M4 (freio anti-alucinação): valida os dados com o schema
    dinâmico e, só se válidos: (1) grava o par (OCR, JSON) na base vetorial da
    configuração (RAG das validações futuras — realimentação do Objetivo 3),
    (2) persiste a nota aprovada em disco (gabarito para avaliações futuras) e
    (3) marca a extração como APROVADA no banco de resultados.

    Levanta `pydantic.ValidationError` se inválido e, nesse caso, NÃO grava
    nada. A página captura o erro e pede à view para exibi-lo."""
    nota = modelo_schema.model_validate(dados)  # levanta ValidationError se inválido
    nota_json = nota.model_dump_json()
    banco.adicionar(texto_ocr, nota_json)
    persistir_aprovada(cfg, imagem_bytes, nota.model_dump_json(indent=2))
    if registro_id:
        registro.atualizar_status(registro_id, "aprovado", json_final=nota_json)
