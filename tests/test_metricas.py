"""
Testes do núcleo metodológico (metricas.py).
============================================
As métricas definem os números do capítulo de Avaliação do TCC — erro aqui
invalida o capítulo inteiro. Rode com:  python -m pytest tests/ -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from experimentos.metricas import (  # noqa: E402
    agregar,
    avaliar_documento,
    campo_correto,
    derivavel_do_ocr,
    distancia_levenshtein,
    normalizar_data,
    normalizar_numero,
    similaridade,
)

CAMPOS = [("company", "texto"), ("address", "texto"), ("date", "data"), ("total", "numero")]


# --- Normalização -----------------------------------------------------------

def test_normalizar_numero_formatos():
    assert normalizar_numero("9.00") == 9.0
    assert normalizar_numero("RM 1,234.56") == 1234.56   # en: vírgula = milhar
    assert normalizar_numero("R$ 1.234,56") == 1234.56   # pt: vírgula = decimal
    assert normalizar_numero("9,00") == 9.0
    assert normalizar_numero(193) == 193.0
    assert normalizar_numero("") is None
    assert normalizar_numero(None) is None


def test_normalizar_data_formatos_sroie():
    assert normalizar_data("25/12/2018") == "2018-12-25"
    assert normalizar_data("25-12-18") == "2018-12-25"
    assert normalizar_data("2018-12-25") == "2018-12-25"
    assert normalizar_data("20181225") == "2018-12-25"
    assert normalizar_data("27 MAR 2018") == "2018-03-27"
    assert normalizar_data("5 March 2018") == "2018-03-05"
    # Irreconhecível: cai para texto normalizado (comparação de string).
    assert normalizar_data("data desconhecida") == "data desconhecida"


# --- Similaridade de edição --------------------------------------------------

def test_levenshtein_basico():
    assert distancia_levenshtein("abc", "abc") == 0
    assert distancia_levenshtein("abc", "abd") == 1
    assert distancia_levenshtein("", "abc") == 3


def test_similaridade_limiar():
    assert similaridade("ojc marketing sdn bhd", "ojc marketing sdn bhd") == 1.0
    # Pequeno ruído de OCR continua acima de 0.8.
    assert similaridade("ojc marketing sdn bhd", "0jc marketlng sdn bhd") >= 0.8
    assert similaridade("empresa a", "empresa b totalmente outra") < 0.8


# --- Casamento (define "correto") --------------------------------------------

def test_campo_correto_por_tipo():
    assert campo_correto("data", "25/12/2018", "25-12-18")
    assert campo_correto("numero", 193.0, "193.00")
    assert campo_correto("numero", "RM193.00", 193.0)
    assert not campo_correto("numero", 193.01, 195.00)
    assert campo_correto("texto", "OJC MARKETING SDN BHD", "ojc marketing sdn  bhd")
    assert not campo_correto("texto", None, "x")  # nulo nunca casa


# --- Derivabilidade (separa alucinação de correção legítima) ------------------

OCR = """OJC MARKETING SDN BHD
NO 2 & 4, JALAN BAYU 4, BANDAR SERI ALAM
15/01/2019 11:03
TOTAL ROUNDED: RM 193.00
"""


def test_derivavel_numero_e_data():
    assert derivavel_do_ocr("numero", 193.0, OCR)
    assert not derivavel_do_ocr("numero", 999.99, OCR)
    assert derivavel_do_ocr("data", "15/01/2019", OCR)
    assert not derivavel_do_ocr("data", "31/12/2020", OCR)


def test_derivavel_texto_com_ruido_de_ocr():
    # O modelo corrigiu "0JC MARKET1NG" do OCR ruidoso -> derivável, não alucinação.
    ocr_ruim = OCR.replace("OJC MARKETING", "0JC MARKET1NG")
    assert derivavel_do_ocr("texto", "OJC MARKETING SDN BHD", ocr_ruim)
    assert not derivavel_do_ocr("texto", "LOJA INVENTADA LTDA", OCR)


# --- Avaliação de documento: TP/FP/FN, alucinação x erro grounded -------------

GABARITO = {
    "company": "OJC MARKETING SDN BHD",
    "address": "NO 2 & 4, JALAN BAYU 4, BANDAR SERI ALAM",
    "date": "15/01/2019",
    "total": "193.00",
}


def test_documento_perfeito():
    previsto = {"company": "OJC Marketing Sdn Bhd",
                "address": "NO 2 & 4, JALAN BAYU 4, BANDAR SERI ALAM",
                "date": "2019-01-15", "total": 193.0}
    av = avaliar_documento(previsto, GABARITO, OCR, CAMPOS)
    assert av["exact_match_doc"] == 1
    assert all(c["tp"] == 1 for c in av["campos"].values())
    assert sum(c["alucinacao"] for c in av["campos"].values()) == 0


def test_alucinacao_vs_erro_grounded():
    # total=999.99: errado vs gabarito E ausente do OCR -> ALUCINAÇÃO.
    # date=15/01/2019 trocada por 11/03/2019? Não: usamos um valor PRESENTE no
    # OCR mas errado vs gabarito (o horário 11:03 não é data...) — em vez disso,
    # company errada mas presente: address no lugar de company -> erro grounded.
    previsto = {"company": "NO 2 & 4, JALAN BAYU 4, BANDAR SERI ALAM",
                "address": None, "date": "15/01/2019", "total": 999.99}
    av = avaliar_documento(previsto, GABARITO, OCR, CAMPOS)
    assert av["campos"]["total"]["alucinacao"] == 1      # inventou valor
    assert av["campos"]["total"]["erro_grounded"] == 0
    assert av["campos"]["company"]["erro_grounded"] == 1  # errado, mas estava no OCR
    assert av["campos"]["company"]["alucinacao"] == 0
    assert av["campos"]["address"]["fn"] == 1             # gabarito tinha, não previu
    assert av["campos"]["address"]["fp"] == 0
    assert av["exact_match_doc"] == 0


def test_prever_campo_que_gabarito_nao_tem_e_fp():
    gab_sem_total = dict(GABARITO, total=None)
    previsto = {"company": "OJC MARKETING SDN BHD", "address": None,
                "date": None, "total": 193.0}
    av = avaliar_documento(previsto, gab_sem_total, OCR, CAMPOS)
    assert av["campos"]["total"]["fp"] == 1
    assert av["campos"]["total"]["fn"] == 0
    # 193.00 está no OCR -> erro grounded, não alucinação.
    assert av["campos"]["total"]["erro_grounded"] == 1


def test_nulo_dos_dois_lados_nao_punido_nem_premiado():
    gab = {"company": "X LTDA", "address": None, "date": None, "total": None}
    previsto = {"company": "X LTDA", "address": None, "date": None, "total": None}
    av = avaliar_documento(previsto, gab, "X LTDA", CAMPOS)
    assert av["exact_match_doc"] == 1
    assert av["campos"]["address"] == {
        "tp": 0, "fp": 0, "fn": 0, "previsto_nao_nulo": 0,
        "alucinacao": 0, "erro_grounded": 0,
    }


# --- Agregação ----------------------------------------------------------------

def test_agregar_prf_e_taxas():
    avs = [
        avaliar_documento(
            {"company": "OJC MARKETING SDN BHD", "address": None,
             "date": "15/01/2019", "total": 999.99},
            GABARITO, OCR, CAMPOS,
        ),
        avaliar_documento(
            {"company": "OJC MARKETING SDN BHD",
             "address": "NO 2 & 4, JALAN BAYU 4, BANDAR SERI ALAM",
             "date": "15/01/2019", "total": 193.0},
            GABARITO, OCR, CAMPOS,
        ),
    ]
    m = agregar(avs, CAMPOS)
    assert m["n_documentos"] == 2
    assert m["exact_match_doc"] == 0.5
    # company: 2 TP; date: 2 TP; address: 1 TP + 1 FN; total: 1 TP + 1 FP+FN.
    assert m["por_campo"]["company"]["f1"] == 1.0
    assert m["por_campo"]["address"]["recall"] == 0.5
    assert m["por_campo"]["address"]["precisao"] == 1.0
    assert m["por_campo"]["total"]["precisao"] == 0.5
    # 1 alucinação (total inventado) sobre 7 campos previstos não-nulos.
    assert m["previstos_nao_nulos"] == 7
    assert abs(m["taxa_alucinacao"] - 1 / 7) < 1e-9
    assert m["taxa_erro_grounded"] == 0.0
