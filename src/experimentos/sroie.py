"""
SROIE (ICDAR 2019, Task 3) — dataset, indexação e salvaguarda anti-leakage.
===========================================================================
A avaliação externa do TCC usa o SROIE como ground truth: recibos reais
(em inglês) anotados com 4 campos — company, address, date e total. O gabarito
vem SEMPRE do dataset; o modelo nunca gera nem corrige a própria referência.

REGRA CRÍTICA (anti-leakage): a base vetorial do RAG é construída SÓ com o
conjunto trainval. As imagens de teste nunca são indexadas nem recuperadas.
Esta regra é ESTRUTURAL aqui, não convenção:
  1. o split é definido pelo DIRETÓRIO (dados/sroie/trainval vs test);
  2. `indexar_trainval` recusa (ValueError) qualquer caminho fora do trainval;
  3. `auditar_colecao` varre os metadados da coleção e ABORTA a avaliação se
     encontrar qualquer documento que não seja do trainval.

Para montar o dataset (1ª vez): python src/sroie.py --preparar
Fonte: espelho HuggingFace `rth/sroie-2019-v2` (dataset oficial do ICDAR 2019,
splits originais: 626 trainval / 347 teste, licença CC-BY-2.0).
"""

# Executável diretamente (python src/experimentos/<script>.py): coloca src/ no
# path para os imports de pacote (nucleo/, experimentos/) resolverem.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


import json
from pathlib import Path
from typing import List, Optional, Tuple

from nucleo.banco_vetorial import BancoVetorial
from nucleo.comum import listar_pares
from nucleo.config import (
    DIR_SROIE_CACHE_OCR,
    DIR_SROIE_TEST,
    DIR_SROIE_TRAINVAL,
    IDIOMA_OCR,
)
from nucleo.ocr import ocr_extrair_texto

# Campos anotados no SROIE, com o TIPO usado pelas métricas (metricas.py).
CAMPOS_SROIE: List[Tuple[str, str]] = [
    ("company", "texto"),
    ("address", "texto"),
    ("date", "data"),
    ("total", "numero"),
]

FONTE_HF = "rth/sroie-2019-v2"  # espelho do dataset oficial


def listar_documentos(diretorio: Path) -> List[Tuple[Path, Path]]:
    """Pares (imagem, gabarito) de um split, ordenados por nome (determinístico)."""
    return listar_pares(diretorio, extensoes=("jpg", "png"))


def carregar_gabarito(caminho_json: Path) -> dict:
    """Gabarito oficial do documento. Strings vazias viram None (campo ausente)."""
    bruto = json.loads(caminho_json.read_text(encoding="utf-8"))
    return {
        chave: (None if valor is None or str(valor).strip() == "" else valor)
        for chave, valor in bruto.items()
    }


def ocr_cacheado(caminho_imagem: Path, split: str) -> str:
    """OCR (Tesseract, inglês) com cache em disco por documento.

    O cache garante o PAREAMENTO ESTRITO da avaliação: o OCR de cada documento
    é feito UMA vez e as duas condições (baseline e RAG) recebem exatamente o
    mesmo texto — além de poupar reprocessamento entre execuções."""
    cache = DIR_SROIE_CACHE_OCR / split / (caminho_imagem.stem + ".txt")
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    texto = ocr_extrair_texto(str(caminho_imagem), idioma=IDIOMA_OCR)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(texto, encoding="utf-8")
    return texto


# ============================================================================
# Indexação (só trainval) e auditoria anti-leakage
# ============================================================================


def _exigir_trainval(caminho: Path) -> None:
    """Garante ESTRUTURALMENTE que só documentos do trainval entram na base."""
    raiz = DIR_SROIE_TRAINVAL.resolve()
    if raiz not in caminho.resolve().parents and caminho.resolve() != raiz:
        raise ValueError(
            f"ANTI-LEAKAGE: tentativa de indexar documento fora do trainval: {caminho}. "
            "O conjunto de teste do SROIE nunca pode entrar na base vetorial."
        )


def indexar_trainval(
    banco: BancoVetorial, limite: Optional[int] = None, verboso: bool = True
) -> int:
    """Indexa pares (OCR, gabarito) do trainval na coleção do experimento.

    O gabarito oficial faz o papel do par humano-validado (como no experimento
    app). Recusa qualquer caminho fora de dados/sroie/trainval."""
    pares = listar_documentos(DIR_SROIE_TRAINVAL)
    if limite:
        pares = pares[:limite]
    for i, (img, js) in enumerate(pares):
        _exigir_trainval(img)
        texto = ocr_cacheado(img, "trainval")
        gabarito = carregar_gabarito(js)
        banco.adicionar(
            texto,
            json.dumps(gabarito, ensure_ascii=False),
            metadados={"doc_id": img.stem, "split": "trainval", "origem": "sroie"},
        )
        if verboso and (i + 1) % 50 == 0:
            print(f"  indexados {i + 1}/{len(pares)}")
    return len(pares)


def auditar_colecao(banco: BancoVetorial) -> int:
    """Auditoria anti-leakage: TODA entrada da coleção precisa ser do trainval.

    Levanta RuntimeError (abortando a avaliação) se encontrar qualquer item de
    teste ou sem rastreabilidade. Devolve o tamanho auditado da coleção."""
    ids_teste = {img.stem for img, _ in listar_documentos(DIR_SROIE_TEST)}
    total = banco.colecao.count()
    if total == 0:
        return 0
    dados = banco.colecao.get(include=["metadatas"])
    for meta in dados["metadatas"]:
        doc_id = meta.get("doc_id")
        if meta.get("split") != "trainval" or doc_id is None:
            raise RuntimeError(
                "ANTI-LEAKAGE: a coleção SROIE contém item sem rastreabilidade "
                f"(metadados: {meta}). Recrie a base com --recriar."
            )
        if doc_id in ids_teste:
            raise RuntimeError(
                f"ANTI-LEAKAGE: documento de TESTE indexado na base ({doc_id}). "
                "Avaliação abortada. Recrie a base com --recriar."
            )
    return total


# ============================================================================
# Preparação do dataset (download único do espelho HuggingFace)
# ============================================================================


def preparar_dataset() -> None:
    """Baixa o SROIE v2 (espelho oficial) e materializa em dados/sroie/
    {trainval,test}/<doc_id>.{jpg,json}. O DIRETÓRIO é a fonte única do split."""
    import pandas as pd
    from huggingface_hub import hf_hub_download

    destinos = {"train": DIR_SROIE_TRAINVAL, "test": DIR_SROIE_TEST}
    for split_hf, destino in destinos.items():
        nome_split = "trainval" if split_hf == "train" else "test"
        if listar_documentos(destino):
            print(f"{destino} já existe — pulando.")
            continue
        parquet = hf_hub_download(
            FONTE_HF, f"data/{split_hf}-00000-of-00001.parquet", repo_type="dataset"
        )
        tabela = pd.read_parquet(parquet)
        destino.mkdir(parents=True, exist_ok=True)
        for i, linha in tabela.iterrows():
            doc_id = f"sroie_{nome_split}_{i:03d}"
            (destino / f"{doc_id}.jpg").write_bytes(linha["image"]["bytes"])
            entidades = {
                chave: (None if valor is None or str(valor).strip() == "" else valor)
                for chave, valor in dict(linha["objects"]["entities"]).items()
            }
            (destino / f"{doc_id}.json").write_text(
                json.dumps(entidades, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        print(f"{nome_split}: {len(tabela)} documentos em {destino}")


def semear_base_do_app() -> None:
    """Indexa o TRAINVAL na coleção do APP (versão atual de campos), para a
    página de Validação já partir com exemplos no RAG em vez de cold start.

    Mantém as coleções SEPARADAS: a do experimento (`sroie_trainval`) continua
    intocada/auditável, e as aprovações do app entram só na coleção do app.
    O guarda anti-leakage vale aqui também: SÓ documentos do trainval entram
    (os de teste continuam proibidos em qualquer base de recuperação)."""
    from nucleo import campos as campos_mod

    cfg = campos_mod.carregar_config()
    chaves = [c["chave"] for c in cfg["campos"]]
    if chaves != [nome for nome, _ in CAMPOS_SROIE]:
        print(
            f"AVISO: os campos atuais do app ({chaves}) diferem do gabarito SROIE "
            f"({[n for n, _ in CAMPOS_SROIE]}). Os exemplos semeados terão as chaves "
            "do SROIE — restaure os campos padrão antes, se quiser exemplos alinhados."
        )
    nome_colecao = campos_mod.nome_colecao_para(cfg)
    banco = BancoVetorial(nome_colecao=nome_colecao)

    # Idempotência: não duplica se a coleção já foi semeada com o SROIE.
    existentes = banco.colecao.get(where={"origem": "sroie"}, include=[])
    if existentes["ids"]:
        print(
            f"A coleção '{nome_colecao}' já tem {len(existentes['ids'])} pares do "
            "SROIE — nada a fazer."
        )
        return
    n = indexar_trainval(banco)
    print(f"{n} pares do trainval semeados em '{nome_colecao}' (total: {banco.contar()}).")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Preparação do dataset SROIE.")
    parser.add_argument("--preparar", action="store_true", help="Baixa e monta dados/sroie/.")
    parser.add_argument(
        "--semear-app",
        action="store_true",
        help="Indexa o trainval na coleção do APP (RAG da página de Validação).",
    )
    args = parser.parse_args()
    if args.preparar:
        preparar_dataset()
    elif args.semear_app:
        semear_base_do_app()
    else:
        print(f"trainval: {len(listar_documentos(DIR_SROIE_TRAINVAL))} documentos")
        print(f"test:     {len(listar_documentos(DIR_SROIE_TEST))} documentos")
        print("(dataset ausente? rode: python src/experimentos/sroie.py --preparar)")
