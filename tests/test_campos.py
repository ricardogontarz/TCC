"""Campos padrão do app — devem ser DERIVADOS do schema do gabarito (fonte
única em nucleo/schema.py). Estes testes quebram se a derivação for
substituída por uma lista duplicada ou se o padrão divergir do ground truth."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nucleo import campos  # noqa: E402
from nucleo.schema import ItemRecibo, ReciboSROIE, campos_do_schema  # noqa: E402


def test_campos_padrao_iguais_ao_gabarito_sroie():
    assert campos.CAMPOS_PADRAO == campos_do_schema(ReciboSROIE)
    assert [(c["chave"], c["tipo"]) for c in campos.CAMPOS_PADRAO] == [
        ("company", "texto"), ("address", "texto"), ("date", "data"), ("total", "numero"),
    ]


def test_config_padrao_alinhada_ao_sroie():
    cfg = campos.CONFIG_PADRAO
    # O gabarito SROIE não anota itens e os recibos são em inglês.
    assert cfg["incluir_itens"] is False
    assert cfg["idioma_ocr"] == "eng"
    assert cfg["campos_item"] == campos_do_schema(ItemRecibo)


def test_assinatura_estavel_e_sensivel_a_campos():
    cfg = campos.CONFIG_PADRAO
    assert campos.assinatura(cfg) == campos.assinatura(dict(cfg))  # determinística
    com_extra = {
        **cfg,
        "campos": cfg["campos"] + [{"chave": "vat", "rotulo": "VAT", "tipo": "numero"}],
    }
    assert campos.assinatura(com_extra) != campos.assinatura(cfg)
