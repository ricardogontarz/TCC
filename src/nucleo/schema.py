"""
Schema de saída — o "contrato" que o LLM precisa seguir.
========================================================
Todos os campos são OPCIONAIS (default None). Isso é o primeiro freio contra
alucinação: quando um dado não está no texto, o modelo DEVE devolver null em
vez de inventar um valor. A validação Pydantic garante o formato; campos
ausentes simplesmente ficam None e não viram erro.

FONTE ÚNICA dos campos: cada campo carrega `tipo` e `rotulo` no
`json_schema_extra`. Os campos PADRÃO do app (nucleo/campos.py) são DERIVADOS
do schema do gabarito (ReciboSROIE) — os campos usados para validar são, por
construção, os mesmos que o formulário e o prompt usam. O usuário pode
adicionar campos extras por cima pela tela de Configurações.
"""

from typing import List, Optional, Type

from pydantic import BaseModel, Field


def _campo(rotulo: str, tipo: str):
    """Campo opcional anotado com o rótulo (formulário) e o tipo lógico
    (texto/numero/data — usado por prompt, formulário e métricas)."""
    return Field(None, json_schema_extra={"rotulo": rotulo, "tipo": tipo})


class ReciboSROIE(BaseModel):
    """Schema do GABARITO do projeto: SROIE (ICDAR 2019, Task 3).
    São exatamente os 4 campos anotados no dataset — o ground truth vem do
    próprio SROIE, nunca do modelo. Todos opcionais (freio anti-alucinação)."""
    company: Optional[str] = _campo("Company", "texto")
    address: Optional[str] = _campo("Address", "texto")
    date: Optional[str] = _campo("Date", "data")        # como impresso no recibo
    total: Optional[float] = _campo("Total", "numero")  # número, sem símbolo de moeda


class ItemRecibo(BaseModel):
    """Colunas PADRÃO de um item/linha do documento, usadas quando o usuário
    LIGA a lista de itens na tela de Configurações (o gabarito SROIE não anota
    itens, então a lista vem desligada por padrão)."""
    descricao: Optional[str] = _campo("Descrição", "texto")
    quantidade: Optional[float] = _campo("Quantidade", "numero")
    valor_unitario: Optional[float] = _campo("Valor unitário", "numero")


def campos_do_schema(modelo: Type[BaseModel]) -> List[dict]:
    """Extrai a lista de campos {chave, rotulo, tipo} de um schema anotado.
    Campos sem anotação de tipo ficam de fora."""
    campos = []
    for chave, campo in modelo.model_fields.items():
        extra = campo.json_schema_extra or {}
        if isinstance(extra, dict) and "tipo" in extra:
            campos.append(
                {"chave": chave, "rotulo": extra.get("rotulo", chave), "tipo": extra["tipo"]}
            )
    return campos
