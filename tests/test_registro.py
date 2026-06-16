"""Testes do banco de RESULTADOS (registro.py) — usa um SQLite temporário."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from nucleo import registro  # noqa: E402


@pytest.fixture
def banco_tmp(tmp_path):
    return str(tmp_path / "resultados_teste.db")


def _registrar(banco_tmp, **kwargs):
    padrao = dict(
        documento_origem="dados/teste/nota_001.png",
        texto_ocr="TEXTO OCR",
        json_extraido='{"fornecedor": "X"}',
        json_valido=True,
        use_rag=True,
        provedor="ollama",
        modelo="llama3.1:8b",
        experimento="cli",
        caminho_banco=banco_tmp,
    )
    padrao.update(kwargs)
    return registro.registrar_extracao(**padrao)


def _linha(banco_tmp, id_):
    con = registro.conectar(banco_tmp)
    con.row_factory = lambda cur, row: {
        d[0]: row[i] for i, d in enumerate(cur.description)
    }
    try:
        return con.execute("SELECT * FROM extracoes WHERE id=?", (id_,)).fetchone()
    finally:
        con.close()


def test_registra_como_pendente_com_versao_do_pipeline(banco_tmp):
    id_ = _registrar(banco_tmp)
    linha = _linha(banco_tmp, id_)
    assert linha["status_validacao"] == "pendente"
    assert linha["versao_pipeline"] == registro.PIPELINE_VERSAO
    assert linha["criado_em"]  # timestamp presente
    assert linha["use_rag"] == 1


def test_aprovacao_atualiza_status_e_json_final(banco_tmp):
    id_ = _registrar(banco_tmp)
    registro.atualizar_status(
        id_, "aprovado", json_final='{"fornecedor": "X corrigido"}',
        caminho_banco=banco_tmp,
    )
    linha = _linha(banco_tmp, id_)
    assert linha["status_validacao"] == "aprovado"
    assert linha["validado_em"] is not None
    assert "corrigido" in linha["json_extraido"]


def test_rejeicao_fica_rastreada(banco_tmp):
    id_ = _registrar(banco_tmp)
    registro.atualizar_status(id_, "rejeitado", caminho_banco=banco_tmp)
    assert _linha(banco_tmp, id_)["status_validacao"] == "rejeitado"


def test_status_invalido_recusado(banco_tmp):
    id_ = _registrar(banco_tmp)
    with pytest.raises(ValueError):
        registro.atualizar_status(id_, "talvez", caminho_banco=banco_tmp)


def test_custo_ollama_zero_e_desconhecido_none():
    assert registro.custo_estimado("ollama", "llama3.1:8b", 1000, 200) == 0.0
    assert registro.custo_estimado("gemini", "modelo-sem-preco", 1000, 200) is None


def test_medias_por_condicao(banco_tmp):
    _registrar(banco_tmp, use_rag=False, duracao_llm_s=4.0, tokens_entrada=700)
    _registrar(banco_tmp, use_rag=False, duracao_llm_s=6.0, tokens_entrada=900)
    _registrar(banco_tmp, use_rag=True, duracao_llm_s=10.0, tokens_entrada=2000)
    medias = registro.medias_por_condicao(caminho_banco=banco_tmp)
    por_condicao = {m["condicao"]: m for m in medias}
    assert por_condicao["SEM RAG"]["n"] == 2
    assert por_condicao["SEM RAG"]["duracao_llm_s"] == 5.0
    assert por_condicao["SEM RAG"]["tokens_entrada"] == 800.0
    assert por_condicao["COM RAG"]["n"] == 1
    assert por_condicao["COM RAG"]["duracao_llm_s"] == 10.0
    # Filtro por experimento: nada registrado como 'app' -> lista vazia.
    assert registro.medias_por_condicao("app", caminho_banco=banco_tmp) == []
