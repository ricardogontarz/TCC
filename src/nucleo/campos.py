"""
Configuração dos campos a extrair (editável pela tela de Configurações do app).
================================================================================
Permite ADICIONAR / REMOVER os campos que o sistema espera extrair das notas,
sem mexer no código. É lido pelo frontend para duas coisas:
  1. montar o prompt de extração (quais campos pedir ao LLM);
  2. renderizar o FORMULÁRIO de revisão (um widget por campo).

Cada campo é um dict simples: {"chave", "rotulo", "tipo"}, onde tipo ∈
{"texto", "numero", "data"}. A lista vive em config.CAMINHO_CAMPOS (campos.json).

IMPORTANTE — escopo: isto afeta o caminho de PRODUÇÃO (app e CLI). A avaliação
SROIE (baseline vs RAG) continua usando o schema FIXO (schema.ReciboSROIE),
porque é o experimento controlado do TCC — o gabarito tem campos fixos. Os
campos PADRÃO abaixo são DERIVADOS de ReciboSROIE: o app já começa alinhado
com o ground truth, e campos extras podem ser adicionados por cima.
"""

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import List, Optional

from nucleo.config import CAMINHO_CAMPOS, CAMINHO_VERSOES, IDIOMA_OCR
from nucleo.schema import ItemRecibo, ReciboSROIE, campos_do_schema

TIPOS_VALIDOS = ("texto", "numero", "data")

# Campos padrão DERIVADOS do schema do GABARITO (FONTE ÚNICA: nucleo/schema.py).
# Os campos que o app pede/mostra por padrão são, por construção, os mesmos
# usados para validar contra o ground truth do SROIE — sem lista duplicada
# para divergir. O usuário pode adicionar campos extras por cima.
CAMPOS_PADRAO: List[dict] = campos_do_schema(ReciboSROIE)
# Colunas PADRÃO de cada item, usadas quando o usuário LIGA a lista de itens
# (desligada por padrão: o gabarito SROIE não anota itens).
CAMPOS_ITEM_PADRAO: List[dict] = campos_do_schema(ItemRecibo)
CONFIG_PADRAO: dict = {
    "campos": CAMPOS_PADRAO,
    "incluir_itens": False,
    "campos_item": CAMPOS_ITEM_PADRAO,
    "idioma_ocr": IDIOMA_OCR,
}


def carregar_config() -> dict:
    """Lê a config de campos. Na primeira vez (arquivo inexistente), cria com os
    campos padrão e devolve uma cópia."""
    caminho = Path(CAMINHO_CAMPOS)
    if not caminho.exists():
        salvar_config(CONFIG_PADRAO)
        return json.loads(json.dumps(CONFIG_PADRAO))  # cópia profunda simples
    cfg = json.loads(caminho.read_text(encoding="utf-8"))
    cfg.setdefault("campos", [])
    cfg.setdefault("incluir_itens", False)
    cfg.setdefault("campos_item", list(CAMPOS_ITEM_PADRAO))
    cfg.setdefault("idioma_ocr", IDIOMA_OCR)
    return cfg


def salvar_config(cfg: dict) -> None:
    """Persiste a config de campos em disco (campos.json)."""
    Path(CAMINHO_CAMPOS).write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def slugificar(rotulo: str) -> str:
    """Deriva uma 'chave' segura (snake_case ASCII) a partir do rótulo digitado.
    Ex.: 'Inscrição Estadual' -> 'inscricao_estadual'. A chave vira o nome do
    campo no JSON, então precisa ser um identificador limpo."""
    base = unicodedata.normalize("NFKD", rotulo).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-zA-Z0-9]+", "_", base).strip("_").lower()
    return base or "campo"


def validar_novo_campo(cfg: dict, rotulo: str, chave: str, tipo: str) -> Optional[str]:
    """Valida a adição de um campo escalar. Devolve mensagem de erro ou None."""
    if not rotulo.strip():
        return "Informe um rótulo para o campo."
    if not chave:
        return "A chave do campo ficou vazia — ajuste o rótulo."
    if tipo not in TIPOS_VALIDOS:
        return f"Tipo inválido (use {', '.join(TIPOS_VALIDOS)})."
    if chave == "itens":
        return "'itens' é reservado para a lista de itens do documento."
    if any(c["chave"] == chave for c in cfg.get("campos", [])):
        return f"Já existe um campo com a chave '{chave}'."
    return None


def validar_novo_campo_item(cfg: dict, rotulo: str, chave: str, tipo: str) -> Optional[str]:
    """Valida a adição de um campo de ITEM/material. Mesma regra do escalar, mas
    a unicidade é dentro de `campos_item` (namespace independente)."""
    if not rotulo.strip():
        return "Informe um rótulo para o campo do item."
    if not chave:
        return "A chave do campo ficou vazia — ajuste o rótulo."
    if tipo not in TIPOS_VALIDOS:
        return f"Tipo inválido (use {', '.join(TIPOS_VALIDOS)})."
    if any(c["chave"] == chave for c in cfg.get("campos_item", [])):
        return f"Já existe um campo de item com a chave '{chave}'."
    return None


def assinatura(cfg: dict) -> str:
    """Hash curto e estável da CONFIGURAÇÃO de campos (não dos valores). Mesma
    config -> mesma assinatura. Usado para nomear a coleção Chroma e a pasta de
    aprovados, de modo que cada conjunto de campos tenha sua PRÓPRIA base."""
    base = {
        "campos": sorted((c["chave"], c["tipo"]) for c in cfg.get("campos", [])),
        "incluir_itens": bool(cfg.get("incluir_itens", False)),
        "campos_item": (
            sorted((c["chave"], c["tipo"]) for c in cfg.get("campos_item", []))
            if cfg.get("incluir_itens", False)
            else []
        ),
    }
    canonico = json.dumps(base, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(canonico.encode("utf-8")).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Versionamento da configuração de campos.
# A assinatura (hash) é a identidade interna; a VERSÃO (v1, v2, ...) é o rótulo
# legível derivado dela. Mudar qualquer campo -> nova assinatura -> nova versão;
# voltar a uma configuração já vista -> reusa a versão dela. Assim mudar campos
# nunca sobrescreve resultados de versões anteriores.
# ---------------------------------------------------------------------------
def _carregar_registro_versoes() -> dict:
    caminho = Path(CAMINHO_VERSOES)
    if not caminho.exists():
        return {"versoes": []}
    return json.loads(caminho.read_text(encoding="utf-8"))


def _salvar_registro_versoes(reg: dict) -> None:
    Path(CAMINHO_VERSOES).write_text(
        json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def versao_dos_campos(cfg: dict) -> int:
    """Número de versão estável da configuração ATUAL de campos. Atribui (e
    persiste) uma versão nova na primeira vez que vê uma assinatura inédita;
    reusa a versão se a assinatura já foi registrada."""
    assn = assinatura(cfg)
    reg = _carregar_registro_versoes()
    for v in reg["versoes"]:
        if v["assinatura"] == assn:
            return v["versao"]
    # Assinatura inédita: cria a próxima versão e guarda um snapshot dos campos
    # (útil para a defesa: dá pra mostrar o que era cada versão).
    proxima = max((v["versao"] for v in reg["versoes"]), default=0) + 1
    reg["versoes"].append(
        {
            "versao": proxima,
            "assinatura": assn,
            "campos": cfg.get("campos", []),
            "incluir_itens": cfg.get("incluir_itens", False),
            "campos_item": cfg.get("campos_item", []) if cfg.get("incluir_itens", False) else [],
        }
    )
    _salvar_registro_versoes(reg)
    return proxima


def listar_versoes() -> list:
    """Histórico de versões registradas (para exibição/auditoria)."""
    return _carregar_registro_versoes()["versoes"]


def nome_colecao_para(cfg: dict) -> str:
    """Nome da coleção Chroma para esta configuração de campos, por VERSÃO
    (ex.: 'notas_v1'). Distinto da coleção da avaliação SROIE
    (config.NOME_COLECAO_SROIE = 'sroie_trainval')."""
    return f"notas_v{versao_dos_campos(cfg)}"
