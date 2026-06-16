"""
M4 — Validação humana (fecha o ciclo de realimentação do Objetivo 3).
=====================================================================
Versão de terminal (decisão do autor: manter no terminal por ora; uma UI
Streamlit/Rails pode vir depois). Só JSON válido (Pydantic) entra na base —
é o que garante que a base de conhecimento não acumule lixo.
"""

from typing import Optional

from pydantic import BaseModel

from nucleo import registro
from nucleo.banco_vetorial import BancoVetorial


def validacao_humana(
    texto_ocr: str,
    dados: BaseModel,
    banco: BancoVetorial,
    registro_id: Optional[str] = None,
) -> None:
    """`registro_id`: id da extração no banco de RESULTADOS — a decisão humana
    (aprovado/rejeitado) fica registrada lá, além de alimentar a base vetorial."""
    print("\n--- JSON EXTRAÍDO ---")
    print(dados.model_dump_json(indent=2))
    resp = input(
        "\nAprovar? [s = sim / c = colar JSON corrigido / n = descartar]: "
    ).strip().lower()

    if resp == "s":
        banco.adicionar(texto_ocr, dados.model_dump_json())
        if registro_id:
            registro.atualizar_status(registro_id, "aprovado")
        print("Aprovado e adicionado à base de conhecimento.")
    elif resp == "c":
        print("Cole o JSON corrigido. Finalize com uma linha contendo apenas: FIM")
        linhas = []
        while True:
            linha = input()
            if linha.strip() == "FIM":
                break
            linhas.append(linha)
        # Valida a correção antes de gravar — só entra JSON válido na base.
        # Usa o MESMO schema do dado extraído (dinâmico, vindo de campos.json).
        dados_corrigidos = type(dados).model_validate_json("\n".join(linhas))
        banco.adicionar(texto_ocr, dados_corrigidos.model_dump_json())
        if registro_id:
            registro.atualizar_status(
                registro_id, "aprovado", json_final=dados_corrigidos.model_dump_json()
            )
        print("Correção validada e adicionada à base.")
    else:
        if registro_id:
            registro.atualizar_status(registro_id, "rejeitado")
        print("Descartado. Nada foi adicionado à base.")
