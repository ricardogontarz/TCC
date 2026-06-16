"""
M4 (web) — Cola de estado do Streamlit (session_state + cache).
===============================================================
Responsabilidade ÚNICA: centralizar TODO o acesso ao `st.session_state` e ao
recurso cacheado (o banco vetorial). É a FONTE ÚNICA dos nomes de key — páginas
e componentes não manipulam strings de key soltas; usam as constantes e
funções daqui. Isso evita typo em key e deixa o ciclo de vida da extração
(semear o formulário / limpar) num só lugar.

Esta camada é deliberadamente "burra": só guarda/recupera estado. A regra de
negócio mora em `servico_nota.py`; a apresentação, em `ui_componentes.py`.
"""

from typing import List, Optional

from pydantic import BaseModel

import streamlit as st

from nucleo.banco_vetorial import BancoVetorial
from nucleo.pipeline import ResultadoExtracao

# --- Fonte única dos nomes de session_state --------------------------------
CHAVE_RESULTADOS: str = "resultados_pareados"  # {"sem_rag": ..., "com_rag": ...}
CHAVE_IMAGEM: str = "imagem"
CHAVE_FLASH: str = "flash"
# Keys dos widgets do formulário de revisão. O prefixo de campo é compartilhado
# com a view (que declara `key=PREFIXO_CAMPO + chave` nos text_inputs); por isso
# mora aqui, dono do namespace de sessão.
PREFIXO_CAMPO: str = "fld_"
CHAVE_ITENS_FORM: str = "fld_itens"   # dados-semente da tabela de itens
CHAVE_EDITOR_ITENS: str = "ed_itens"  # key do widget st.data_editor


@st.cache_resource(show_spinner="Carregando banco vetorial e modelo de embedding…")
def carregar_banco(nome_colecao: str) -> BancoVetorial:
    """Carrega o banco (e o modelo de embedding, que é pesado) por COLEÇÃO.
    O `@st.cache_resource` chaveia pelo argumento, então cada configuração de
    campos (que define um `nome_colecao` próprio) ganha sua própria instância
    cacheada — uma base por configuração, sem recarregar o embedding a cada clique."""
    return BancoVetorial(nome_colecao=nome_colecao)


def _valor_str(valor) -> str:
    """None -> '' (campo vazio no form); demais -> string para o widget."""
    return "" if valor is None else str(valor)


def limpar_extracao() -> None:
    """Esquece a extração atual (as duas condições) e os valores do formulário
    (após gravar ou descartar), liberando a tela para o próximo documento."""
    for chave in list(st.session_state.keys()):
        if chave in (
            CHAVE_RESULTADOS, CHAVE_IMAGEM, CHAVE_EDITOR_ITENS
        ) or chave.startswith(PREFIXO_CAMPO):
            st.session_state.pop(chave, None)


def set_resultados(resultados: dict, imagem: bytes) -> None:
    """Guarda a extração pareada corrente ({"sem_rag": ..., "com_rag": ...}) e
    os bytes da imagem original na sessão."""
    st.session_state[CHAVE_RESULTADOS] = resultados
    st.session_state[CHAVE_IMAGEM] = imagem


def get_resultados() -> Optional[dict]:
    """Devolve a extração pareada corrente (ou None se ainda não houve)."""
    return st.session_state.get(CHAVE_RESULTADOS)


def condicao_revisao(resultados: dict) -> Optional[str]:
    """Qual condição vai para a REVISÃO: sempre a COM RAG (regra do produto —
    o baseline é só referência de comparação). Se a COM RAG falhou, cai para a
    SEM RAG; se ambas falharam, None (nada a revisar)."""
    for condicao in ("com_rag", "sem_rag"):
        if resultados.get(condicao) is not None and resultados[condicao].nota is not None:
            return condicao
    return None


def get_resultado() -> Optional[ResultadoExtracao]:
    """Devolve o ResultadoExtracao da condição EM REVISÃO (ou None)."""
    resultados = get_resultados()
    if resultados is None:
        return None
    condicao = condicao_revisao(resultados)
    return resultados.get(condicao) if condicao else None


def get_imagem() -> Optional[bytes]:
    """Devolve os bytes da imagem da nota corrente (ou None)."""
    return st.session_state.get(CHAVE_IMAGEM)


def prefill_formulario(cfg: dict, nota: BaseModel) -> None:
    """Pré-preenche o formulário de revisão com os valores extraídos (em
    strings), por campo da config + a tabela de itens.

    CRÍTICO (gotcha do Streamlit): escrever numa key de widget só é permitido
    ANTES de o widget ser instanciado no mesmo run. Por isso o controlador da
    página chama isto no handler do "Extrair" (upstream do formulário), e a
    view jamais escreve essas keys."""
    dados = nota.model_dump()
    for campo in cfg["campos"]:
        st.session_state[PREFIXO_CAMPO + campo["chave"]] = _valor_str(
            dados.get(campo["chave"])
        )
    if cfg.get("incluir_itens", True):
        chaves_item = [c["chave"] for c in cfg.get("campos_item", [])]
        itens = [
            {ch: _valor_str(it.get(ch)) for ch in chaves_item}
            for it in (dados.get("itens") or [])
        ]
        # Sem itens: semeia uma linha-modelo vazia (com as colunas configuradas)
        # para a tabela exibir as colunas (linhas em branco somem no save).
        st.session_state[CHAVE_ITENS_FORM] = itens or [
            {ch: "" for ch in chaves_item}
        ]


def ler_valores_campos(cfg: dict) -> dict:
    """Lê os valores crus (string) digitados no formulário, por chave de campo.
    Chamado no submit para o serviço montar/validar os dados."""
    return {
        campo["chave"]: st.session_state.get(PREFIXO_CAMPO + campo["chave"], "")
        for campo in cfg["campos"]
    }


def get_itens_form() -> List[dict]:
    """Dados-semente da tabela de itens (o que o data_editor exibe inicialmente)."""
    return st.session_state.get(CHAVE_ITENS_FORM, [])


def set_flash(mensagem: str) -> None:
    """Agenda uma mensagem de sucesso para o PRÓXIMO run (após o rerun que
    segue a gravação)."""
    st.session_state[CHAVE_FLASH] = mensagem


def pop_flash() -> Optional[str]:
    """Consome (lê e remove) a mensagem de flash pendente, se houver."""
    return st.session_state.pop(CHAVE_FLASH, None)
