"""
Avaliação externa com o SROIE (ICDAR 2019) — baseline (LLM puro) vs LLM + RAG.
==============================================================================
Roda os MESMOS documentos de teste pelos dois pipelines e compara com o
ground truth oficial do dataset (nunca gerado/corrigido pelo modelo).

Desenho experimental:
  - Base vetorial construída SÓ com o trainval (626 docs) — auditoria
    anti-leakage obrigatória antes de medir (sroie.auditar_colecao).
  - PAREAMENTO ESTRITO: o OCR de cada documento de teste é feito uma única vez
    (cache em disco) e as duas condições recebem exatamente o mesmo texto,
    mesmo modelo, mesma ordem de documentos.
  - Métricas (metricas.py): Precisão/Recall/F1 por campo + micro; taxa de
    alucinação (principal: errado vs gabarito E não derivável do OCR); taxa de
    erro "grounded" (errado mas presente no OCR); validade do JSON; exact match
    por documento; tempo e custo por documento (secundárias).
  - Toda extração é registrada no banco de RESULTADOS (registro.py).

Uso:
  python src/avaliacao_sroie.py --recriar                 # indexa trainval e avalia tudo
  python src/avaliacao_sroie.py --limite 5 --pausa 0      # smoke test (base já indexada)
  python src/avaliacao_sroie.py --provedor ollama --modelo qwen2.5:7b
"""

# Executável diretamente (python src/experimentos/<script>.py): coloca src/ no
# path para os imports de pacote (nucleo/, experimentos/) resolverem.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


import argparse
import csv
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # backend headless: salva PNG sem abrir janela
import matplotlib.pyplot as plt

from nucleo import registro
from experimentos import sroie
from nucleo.banco_vetorial import BancoVetorial
from nucleo.comum import slug_modelo, tolerar_rate_limit
from nucleo.config import (
    LIMIAR_DERIVACAO,
    LIMIAR_SIMILARIDADE,
    MODELO_LLM,
    MODELO_OLLAMA,
    NOME_COLECAO_SROIE,
    PIPELINE_VERSAO,
    PROVEDOR_LLM,
)
from experimentos.metricas import agregar, avaliar_documento
from nucleo.pipeline import INSTRUCOES, ResultadoExtracao, extrair
from nucleo.schema import ReciboSROIE
from experimentos.sroie import CAMPOS_SROIE

NOMES_CAMPOS = [nome for nome, _ in CAMPOS_SROIE]


def _extrair_resiliente(
    img: Path,
    texto_ocr: str,
    banco: BancoVetorial,
    use_rag: bool,
    provedor: str,
    modelo: str,
) -> ResultadoExtracao:
    """Extração do SROIE (schema + instruções próprios), tolerando rate-limit."""
    return tolerar_rate_limit(
        lambda: extrair(
            str(img),
            banco,
            use_rag=use_rag,
            retornar_metadados=True,
            provedor=provedor,
            modelo=modelo,
            modelo_schema=ReciboSROIE,
            texto_ocr=texto_ocr,
            instrucoes=INSTRUCOES,
        ),
        rotulo=img.name,
    )


def avaliar(args, provedor: str, modelo: str) -> dict:
    """Loop pareado: para cada documento de teste, roda baseline e RAG sobre o
    MESMO texto OCR. Devolve {condicao: {metricas..., instrumentação...}}."""
    banco = BancoVetorial(nome_colecao=NOME_COLECAO_SROIE)

    if args.recriar and banco.colecao.count() > 0:
        banco.cliente.delete_collection(NOME_COLECAO_SROIE)
        banco = BancoVetorial(nome_colecao=NOME_COLECAO_SROIE)
        print("Coleção SROIE recriada do zero.")

    if banco.colecao.count() == 0:
        print("Indexando o trainval (OCR + embeddings — primeira vez demora)...")
        n = sroie.indexar_trainval(banco, limite=args.limite_indexacao)
        print(f"Base indexada com {n} documentos do trainval.")

    # Auditoria anti-leakage: aborta se houver QUALQUER item fora do trainval.
    total_base = sroie.auditar_colecao(banco)
    print(f"Auditoria anti-leakage: OK ({total_base} itens, todos do trainval).")

    pares = sroie.listar_documentos(sroie.DIR_SROIE_TEST)
    if args.limite:
        pares = pares[: args.limite]
    print(f"Avaliando {len(pares)} documentos de teste nas DUAS condições...\n")

    acum = {
        cond: {
            "avaliacoes": [],
            "validos_1a": 0,
            "validos_final": 0,
            "falhas": 0,
            "tempo_llm": 0.0,
            "tokens_entrada": 0,
            "tokens_saida": 0,
            "tem_tokens": 0,
            "custo": 0.0,
            "tem_custo": 0,
        }
        for cond in ("sem_rag", "com_rag")
    }

    for i, (img, js) in enumerate(pares):
        if args.pausa and i > 0:
            time.sleep(args.pausa)
        gabarito = sroie.carregar_gabarito(js)
        texto_ocr = sroie.ocr_cacheado(img, "test")  # OCR único -> pareamento estrito

        for use_rag in (False, True):
            cond = "com_rag" if use_rag else "sem_rag"
            a = acum[cond]
            try:
                resultado = _extrair_resiliente(
                    img, texto_ocr, banco, use_rag, provedor, modelo
                )
            except Exception as erro:
                print(f"  [aviso] {img.name} ({cond}): falha ao extrair ({erro}).")
                a["falhas"] += 1
                # Documento conta nas métricas: tudo que o gabarito tem vira FN.
                a["avaliacoes"].append(
                    avaliar_documento({}, gabarito, texto_ocr, CAMPOS_SROIE)
                )
                continue

            previsto = resultado.nota.model_dump() if resultado.nota else {}
            a["avaliacoes"].append(
                avaliar_documento(previsto, gabarito, texto_ocr, CAMPOS_SROIE)
            )
            a["validos_1a"] += int(resultado.valido_primeira)
            a["validos_final"] += int(resultado.nota is not None)
            if resultado.duracao_llm_s:
                a["tempo_llm"] += resultado.duracao_llm_s
            if resultado.tokens_entrada is not None:
                a["tokens_entrada"] += resultado.tokens_entrada
                a["tokens_saida"] += resultado.tokens_saida or 0
                a["tem_tokens"] += 1
            custo = registro.custo_estimado(
                provedor, modelo, resultado.tokens_entrada, resultado.tokens_saida
            )
            if custo is not None:
                a["custo"] += custo
                a["tem_custo"] += 1

            # Histórico completo no banco de resultados (status: pendente —
            # a avaliação é automática, não há validação humana aqui).
            resultado.registro_id = registro.registrar_resultado(
                resultado,
                documento_origem=str(img),
                use_rag=use_rag,
                provedor=provedor,
                modelo=modelo,
                experimento="sroie",
                custo_usd=custo,
            )
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(pares)} documentos avaliados.")

    saida = {}
    for cond, a in acum.items():
        n = len(pares)
        m = agregar(a["avaliacoes"], CAMPOS_SROIE)
        m["taxa_json_valido_1a"] = a["validos_1a"] / n if n else 0.0
        m["taxa_json_valido_final"] = a["validos_final"] / n if n else 0.0
        m["n_falhas"] = a["falhas"]
        m["tempo_llm_medio_s"] = a["tempo_llm"] / n if n else 0.0
        m["tokens_medios_entrada"] = (
            a["tokens_entrada"] / a["tem_tokens"] if a["tem_tokens"] else None
        )
        m["tokens_medios_saida"] = (
            a["tokens_saida"] / a["tem_tokens"] if a["tem_tokens"] else None
        )
        m["custo_medio_usd"] = a["custo"] / a["tem_custo"] if a["tem_custo"] else None
        saida[cond] = m
    return saida


# ============================================================================
# Saídas: CSV (dados), Markdown (tabela do relatório) e gráfico (F1 por campo)
# ============================================================================


def _fmt(v, casas=3):
    if v is None:
        return "—"
    return f"{v:.{casas}f}"


def gerar_csv(resultados: dict, caminho: Path, modelo_label: str) -> None:
    com, sem = resultados["com_rag"], resultados["sem_rag"]
    linhas = [("metrica", "SEM_RAG (baseline)", "COM_RAG")]
    linhas.append(("modelo", modelo_label, modelo_label))
    linhas.append(("versao_pipeline", PIPELINE_VERSAO, PIPELINE_VERSAO))
    linhas.append(("limiar_similaridade", str(LIMIAR_SIMILARIDADE), str(LIMIAR_SIMILARIDADE)))
    linhas.append(("limiar_derivacao", str(LIMIAR_DERIVACAO), str(LIMIAR_DERIVACAO)))
    for campo in NOMES_CAMPOS:
        for met in ("precisao", "recall", "f1"):
            linhas.append(
                (
                    f"{met}_{campo}",
                    _fmt(sem["por_campo"][campo][met]),
                    _fmt(com["por_campo"][campo][met]),
                )
            )
    for chave, rotulo in [
        ("precisao", "precisao_micro"), ("recall", "recall_micro"), ("f1", "f1_micro")
    ]:
        linhas.append((rotulo, _fmt(sem["micro"][chave]), _fmt(com["micro"][chave])))
    for chave in (
        "taxa_alucinacao",
        "taxa_erro_grounded",
        "exact_match_doc",
        "taxa_json_valido_1a",
        "taxa_json_valido_final",
        "tempo_llm_medio_s",
        "tokens_medios_entrada",
        "tokens_medios_saida",
        "custo_medio_usd",
    ):
        linhas.append((chave, _fmt(sem.get(chave)), _fmt(com.get(chave))))
    linhas.append(("n_documentos", str(sem["n_documentos"]), str(com["n_documentos"])))
    linhas.append(("n_falhas", str(sem["n_falhas"]), str(com["n_falhas"])))

    with caminho.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(linhas)
    print(f"CSV salvo em {caminho}")


def gerar_markdown(resultados: dict, caminho: Path, modelo_label: str) -> None:
    """Tabela pronta para colar na seção de Avaliação/Testes do relatório."""
    com, sem = resultados["com_rag"], resultados["sem_rag"]
    md = [
        f"### SROIE (ICDAR 2019) — baseline vs RAG — {modelo_label}",
        "",
        f"- Documentos de teste: **{com['n_documentos']}** (base RAG: trainval, "
        "auditada contra leakage)",
        f"- Limiar de similaridade (company/address): **{LIMIAR_SIMILARIDADE}** | "
        f"limiar de derivação (alucinação): **{LIMIAR_DERIVACAO}** | "
        f"pipeline v{PIPELINE_VERSAO}",
        "",
        "| Campo | P (base) | R (base) | F1 (base) | P (RAG) | R (RAG) | F1 (RAG) |",
        "|---|---|---|---|---|---|---|",
    ]
    for campo in NOMES_CAMPOS:
        s, c = sem["por_campo"][campo], com["por_campo"][campo]
        md.append(
            f"| {campo} | {_fmt(s['precisao'])} | {_fmt(s['recall'])} | {_fmt(s['f1'])} "
            f"| {_fmt(c['precisao'])} | {_fmt(c['recall'])} | {_fmt(c['f1'])} |"
        )
    md.append(
        f"| **micro** | {_fmt(sem['micro']['precisao'])} | {_fmt(sem['micro']['recall'])} "
        f"| {_fmt(sem['micro']['f1'])} | {_fmt(com['micro']['precisao'])} "
        f"| {_fmt(com['micro']['recall'])} | {_fmt(com['micro']['f1'])} |"
    )
    md += [
        "",
        "| Métrica | Baseline (LLM puro) | LLM + RAG |",
        "|---|---|---|",
        f"| Taxa de alucinação (principal) | {_fmt(sem['taxa_alucinacao'])} | {_fmt(com['taxa_alucinacao'])} |",
        f"| Taxa de erro grounded | {_fmt(sem['taxa_erro_grounded'])} | {_fmt(com['taxa_erro_grounded'])} |",
        f"| Exact match (documento) | {_fmt(sem['exact_match_doc'])} | {_fmt(com['exact_match_doc'])} |",
        f"| JSON válido (1ª tentativa) | {_fmt(sem['taxa_json_valido_1a'])} | {_fmt(com['taxa_json_valido_1a'])} |",
        f"| JSON válido (final) | {_fmt(sem['taxa_json_valido_final'])} | {_fmt(com['taxa_json_valido_final'])} |",
        f"| Tempo LLM médio/doc (s) | {_fmt(sem['tempo_llm_medio_s'], 1)} | {_fmt(com['tempo_llm_medio_s'], 1)} |",
        f"| Tokens médios (entrada) | {_fmt(sem['tokens_medios_entrada'], 0)} | {_fmt(com['tokens_medios_entrada'], 0)} |",
        f"| Custo médio/doc (US$) | {_fmt(sem['custo_medio_usd'], 4)} | {_fmt(com['custo_medio_usd'], 4)} |",
    ]
    caminho.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Markdown salvo em {caminho}")


def gerar_grafico(resultados: dict, caminho: Path, modelo_label: str) -> None:
    com, sem = resultados["com_rag"], resultados["sem_rag"]
    x = range(len(NOMES_CAMPOS))
    largura = 0.38
    f1_sem = [sem["por_campo"][c]["f1"] for c in NOMES_CAMPOS]
    f1_com = [com["por_campo"][c]["f1"] for c in NOMES_CAMPOS]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.bar([i - largura / 2 for i in x], f1_sem, largura, label="Baseline (LLM puro)")
    ax.bar([i + largura / 2 for i in x], f1_com, largura, label="LLM + RAG")
    ax.set_ylabel("F1 por campo")
    ax.set_title(f"SROIE — F1 por campo: baseline vs RAG\nModelo: {modelo_label}")
    ax.set_xticks(list(x))
    ax.set_xticklabels(NOMES_CAMPOS)
    ax.set_ylim(0, 1.05)
    ax.legend()
    fig.tight_layout()
    fig.savefig(caminho, dpi=150)
    plt.close(fig)
    print(f"Gráfico salvo em {caminho}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Avaliação SROIE: baseline (LLM puro) vs LLM + RAG."
    )
    parser.add_argument("--recriar", action="store_true",
                        help="Apaga e reindexa a coleção SROIE (experimento limpo).")
    parser.add_argument("--limite", type=int, default=None,
                        help="Avalia só os N primeiros docs de teste (smoke test).")
    parser.add_argument("--limite-indexacao", type=int, default=None,
                        help="Indexa só os N primeiros docs do trainval (smoke test).")
    parser.add_argument("--provedor", choices=["ollama", "gemini"], default=None)
    parser.add_argument("--modelo", default=None)
    parser.add_argument("--pausa", type=float, default=0.0,
                        help="Segundos entre documentos (free tier do Gemini: use 8).")
    parser.add_argument("--saida", default=None,
                        help="Prefixo das saídas. Default: resultados/sroie_<modelo>")
    args = parser.parse_args()

    provedor = args.provedor or PROVEDOR_LLM
    modelo = args.modelo or (MODELO_OLLAMA if provedor == "ollama" else MODELO_LLM)
    modelo_label = f"{provedor} / {modelo}"
    slug = slug_modelo(provedor, modelo)
    prefixo = Path(args.saida or f"resultados/sroie_{slug}")
    prefixo.parent.mkdir(parents=True, exist_ok=True)

    print(f"Modelo: {modelo_label} | pipeline v{PIPELINE_VERSAO}")
    resultados = avaliar(args, provedor, modelo)

    gerar_csv(resultados, prefixo.with_suffix(".csv"), modelo_label)
    gerar_markdown(resultados, prefixo.with_suffix(".md"), modelo_label)
    gerar_grafico(resultados, prefixo.with_suffix(".png"), modelo_label)

    com, sem = resultados["com_rag"], resultados["sem_rag"]
    print("\n=== RESUMO (SROIE) ===")
    print(f"F1 micro          baseline: {sem['micro']['f1']:.3f} | RAG: {com['micro']['f1']:.3f}")
    print(f"Alucinação        baseline: {sem['taxa_alucinacao']:.3f} | RAG: {com['taxa_alucinacao']:.3f}")
    print(f"Exact match doc   baseline: {sem['exact_match_doc']:.3f} | RAG: {com['exact_match_doc']:.3f}")
    print(f"JSON válido 1ª    baseline: {sem['taxa_json_valido_1a']:.3f} | RAG: {com['taxa_json_valido_1a']:.3f}")


if __name__ == "__main__":
    main()
