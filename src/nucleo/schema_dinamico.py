"""
Schema Pydantic DINÂMICO, montado a partir da config de campos (campos.py).
============================================================================
O caminho de produção (app) usa campos configuráveis pelo usuário. Este módulo
transforma essa configuração num modelo Pydantic real — assim reaproveitamos
EXATAMENTE os mesmos freios do schema fixo:
  - model_json_schema()  -> alimenta o prompt (diz ao LLM o formato esperado);
  - model_validate()/_json() -> 2º freio anti-alucinação (valida a saída).

Os campos são todos Optional (campo ausente = null, nunca inventado), igual ao
schema fixo. Tanto os campos do TOPO do documento quanto os campos de cada ITEM
(material) são dinâmicos — vêm de `campos.py` (cfg["campos"] e cfg["campos_item"]).
"""

from typing import List, Optional, Type

from pydantic import BaseModel, Field, create_model

# Mapeia o "tipo" da config para o tipo Python usado na validação.
_TIPO_PY = {
    "texto": Optional[str],
    "numero": Optional[float],
    "data": Optional[str],  # data fica como string ISO (aaaa-mm-dd), como no fixo
}


def construir_item(cfg: dict) -> Type[BaseModel]:
    """Monta o modelo de um ITEM/material a partir de cfg["campos_item"]. Cada
    campo do item vira um atributo Optional (ex.: descricao, quantidade,
    valor_unitario e quaisquer adicionados pelo usuário, como unidade/NCM)."""
    definicoes = {}
    for campo in cfg.get("campos_item", []):
        tipo_py = _TIPO_PY.get(campo.get("tipo"), Optional[str])
        definicoes[campo["chave"]] = (tipo_py, None)
    return create_model("ItemDinamico", **definicoes)


def construir_modelo(cfg: dict) -> Type[BaseModel]:
    """Monta o modelo Pydantic da nota a partir da config. Cada campo escalar
    vira um atributo Optional; se incluir_itens, adiciona `itens` como uma lista
    de itens DINÂMICOS (campos definidos em cfg["campos_item"])."""
    definicoes = {}
    for campo in cfg.get("campos", []):
        tipo_py = _TIPO_PY.get(campo.get("tipo"), Optional[str])
        # (tipo, default) — None deixa o campo opcional (não inventar).
        definicoes[campo["chave"]] = (tipo_py, None)

    if cfg.get("incluir_itens", True):
        Item = construir_item(cfg)
        definicoes["itens"] = (List[Item], Field(default_factory=list))

    # create_model gera a classe em tempo de execução, equivalente a declarar
    # `class NotaDinamica(BaseModel): ...` com esses campos.
    return create_model("NotaDinamica", **definicoes)
