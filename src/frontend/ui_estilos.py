"""
M4 (web) — Identidade visual (camada de apresentação/tema).
===========================================================
Responsabilidade ÚNICA: injetar o CSS do frontend. Tudo aqui é cosmético e
segue o tema (claro/escuro) do usuário: superfícies translúcidas + texto
herdado, para nenhum componente customizado quebrar no tema escuro.

Não chama `st.*` em nível de módulo — o CSS só é injetado quando o roteador
(`app.py`) invoca `injetar_css()`, depois do `st.set_page_config`.
"""

import streamlit as st


def injetar_css() -> None:
    """Injeta o tema customizado uma única vez (chamado pelo roteador)."""
    st.markdown(
        """
        <style>
        :root {
            --cor-texto-suave: #64748b;
            --superficie:    rgba(128, 128, 128, 0.08);
            --superficie-2:  rgba(128, 128, 128, 0.12);
            --borda-suave:   rgba(128, 128, 128, 0.22);
        }
        .block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1280px; }

        .app-hero {
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
            color: #fff; border-radius: 18px; padding: 1.5rem 1.8rem;
            margin-bottom: 1.4rem; box-shadow: 0 10px 30px rgba(79, 70, 229, 0.25);
        }
        .app-hero h1 { font-size: 1.7rem; font-weight: 700; margin: 0 0 .35rem 0; color: #fff; line-height: 1.2; }
        .app-hero p { margin: 0; font-size: .98rem; color: rgba(255, 255, 255, 0.88); max-width: 760px; }

        .card {
            background: var(--superficie); border: 1px solid var(--borda-suave);
            border-radius: 14px; padding: 1.1rem 1.25rem; margin-bottom: 1rem;
        }

        .empty-state {
            text-align: center; padding: 2.6rem 1.5rem; border: 1.5px dashed var(--borda-suave);
            border-radius: 16px; background: var(--superficie);
        }
        .empty-state .emoji { font-size: 2.6rem; display: block; margin-bottom: .5rem; }
        .empty-state h3 { margin: 0 0 .4rem 0; font-size: 1.15rem; }
        .empty-state > div { opacity: .75; }
        .empty-state ol { text-align: left; max-width: 420px; margin: .8rem auto 0; line-height: 1.7; opacity: .85; }

        .badge {
            display: inline-flex; align-items: center; gap: .35rem; padding: .22rem .7rem;
            border-radius: 999px; font-size: .8rem; font-weight: 600; line-height: 1; margin: 0 .3rem .3rem 0;
        }
        .badge-ok    { background: #dcfce7; color: #166534; }
        .badge-warn  { background: #fef3c7; color: #92400e; }
        .badge-info  { background: #e0e7ff; color: #3730a3; }
        .badge-muted { background: #e2e8f0; color: #475569; }

        /* Linha campo→valor nos cartões da comparação baseline vs RAG. */
        .campo-comparacao { margin: 0 0 .35rem 0; line-height: 1.45; word-break: break-word; }
        .campo-comparacao .badge { min-width: 6.5rem; justify-content: center; }

        .stButton > button { border-radius: 10px; font-weight: 600; transition: all .15s ease; }
        .stButton > button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0, 0, 0, 0.18); }

        section[data-testid="stSidebar"] { border-right: 1px solid var(--borda-suave); }
        section[data-testid="stSidebar"] .block-container { padding-top: 1.5rem; }

        /* --- Navegação (sidebar): marca + radio estilizado como menu --- */
        .nav-brand { padding: .2rem .2rem .9rem .2rem; }
        .nav-brand-titulo { font-size: 1.25rem; font-weight: 800; letter-spacing: .2px; }
        .nav-brand-sub { font-size: .8rem; opacity: .65; margin-top: .15rem; }

        section[data-testid="stSidebar"] div[role="radiogroup"] > label {
            display: flex; align-items: center;
            padding: .55rem .8rem; margin: 0 0 .3rem 0;
            border-radius: 10px; border: 1px solid transparent;
            transition: background .15s ease, border-color .15s ease;
            cursor: pointer; width: 100%;
        }
        section[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
            background: rgba(99, 102, 241, 0.10);
        }
        /* item ativo (o label que contém o radio marcado) */
        section[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
            background: rgba(99, 102, 241, 0.16);
            border-color: rgba(99, 102, 241, 0.35);
            font-weight: 700;
        }
        /* esconde a bolinha do radio — o destaque do item ativo já comunica */
        section[data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child {
            display: none;
        }

        .nav-rodape {
            font-size: .75rem; opacity: .55; padding: .4rem .2rem;
            text-align: center;
        }

        div[data-testid="stMetric"] {
            background: var(--superficie-2); border: 1px solid var(--borda-suave);
            border-radius: 12px; padding: .8rem 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
