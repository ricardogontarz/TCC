"""
M4 (web) — Roteador do frontend de validação humana (Streamlit).
================================================================
Três páginas (seletor na barra lateral):
  • Validação    — upload → extração → revisão em FORMULÁRIO → aprovar/corrigir.
  • Dashboard    — histórico de extrações (status/tempos) + resultados das avaliações.
  • Configurações — adicionar/remover os CAMPOS que se espera extrair (campos.py).

Responsabilidade ÚNICA deste arquivo: ROTEAR. A aparência vive em `ui_estilos`/
`ui_componentes`, o estado da sessão em `ui_estado`, a regra de negócio em
`servico_nota` e a orquestração de cada tela em `pagina_validacao`/
`pagina_configuracoes`. Aqui só fica o que é global: `set_page_config`, o tema
e a navegação. O banco NÃO é mais carregado aqui: como cada configuração de
campos usa sua própria coleção, é a página de Validação que resolve qual base
abrir (a de Configurações não precisa de banco).

Rode SEMPRE a partir da raiz do projeto (caminhos relativos do config):

    streamlit run src/app.py
"""

import streamlit as st

from frontend import pagina_configuracoes, pagina_dashboard, pagina_validacao, ui_estilos
from nucleo.config import PIPELINE_VERSAO

# 1) set_page_config PRECISA ser a primeira chamada Streamlit (restrição do framework).
st.set_page_config(
    page_title="Extração de Documentos — RAG + OCR",
    page_icon="🧾",
    layout="wide",
)

# 2) Tema (cosmético) — depois do page_config.
ui_estilos.injetar_css()

# 3) Navegação entre páginas (rótulo com ícone -> página; fonte única daqui).
PAGINAS = {
    "🧾  Validação": pagina_validacao,
    "📊  Dashboard": pagina_dashboard,
    "⚙️  Configurações": pagina_configuracoes,
}
st.sidebar.markdown(
    """
    <div class="nav-brand">
        <div class="nav-brand-titulo">🧾 RAG + OCR</div>
        <div class="nav-brand-sub">Extração validada de documentos</div>
    </div>
    """,
    unsafe_allow_html=True,
)
pagina = st.sidebar.radio(
    "Navegação", list(PAGINAS), label_visibility="collapsed", key="nav_pagina"
)
st.sidebar.divider()

# 4) Despacha para a página escolhida (cada página resolve seus próprios recursos).
PAGINAS[pagina].render()

# 5) Rodapé da navegação (versão carimbada em toda extração — registro.py).
st.sidebar.markdown(
    f'<div class="nav-rodape">pipeline v{PIPELINE_VERSAO} · TCC UTFPR-DV</div>',
    unsafe_allow_html=True,
)
