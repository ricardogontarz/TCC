"""
Dashboard — visão consolidada da ferramenta.
============================================
Duas abas, alimentadas pelas duas camadas de persistência:

1. **Extrações** (banco de RESULTADOS, SQLite via `nucleo.registro`): contagens
   por status da validação humana (pendente/aprovado/rejeitado), custo
   (US$ e R$, via config.CAMBIO_USD_BRL), tempos/tokens médios por condição,
   volume por experimento/dia e a tabela das extrações recentes.
2. **Avaliações** (artefatos de `resultados/`): as tabelas baseline vs RAG do
   SROIE (Markdown gerado pelo harness) e os gráficos (PNG).

Página só de LEITURA: nenhum botão aqui altera base nenhuma.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from nucleo import registro
from nucleo.config import CAMBIO_USD_BRL

DIR_RESULTADOS = Path("resultados")

# Colunas exibidas na tabela de extrações (conteúdo OCR/JSON fica de fora de
# propósito: pesado e potencialmente sensível — está no banco, não na tela).
COLUNAS_TABELA = [
    "criado_em", "experimento", "documento_origem", "use_rag", "provedor",
    "modelo", "json_valido", "status_validacao", "versao_pipeline",
    "duracao_total_s", "tokens_entrada", "tokens_saida", "custo_usd",
]

ROTULOS_STATUS = {"pendente": "⏳ Pendentes", "aprovado": "✅ Aprovadas", "rejeitado": "🗑️ Rejeitadas"}

# Rótulos amigáveis no filtro. O 'cli' fica FORA das opções de propósito
# (uso pontual de terminal — ruído na análise); a opção "todos" continua
# contando tudo o que está no banco.
ROTULOS_EXPERIMENTO = {
    "todos": "🌐 Todos",
    "app": "🖥️ App (validação humana)",
    "sroie": "🧪 Avaliação SROIE",
}
EXPERIMENTOS_OCULTOS = {"cli"}


def render_hero() -> None:
    st.markdown(
        """
        <div class="app-hero">
            <h1>📊 Dashboard</h1>
            <p>Histórico de <b>extrações</b> (status da validação humana, tempos e
            <b>custo</b>) e <b>resultados das avaliações</b> — baseline (LLM puro) vs LLM + RAG.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Aba 1 — Extrações (resultados.db)
# ---------------------------------------------------------------------------


def _com_custo(df: pd.DataFrame) -> pd.DataFrame:
    """Garante a coluna de custo: usa o valor gravado e ESTIMA o que faltar a
    partir de provedor/modelo/tokens (None quando o preço não está cadastrado
    — melhor não reportar do que reportar errado)."""
    def estimar(linha):
        if linha.get("custo_usd") is not None:
            return linha["custo_usd"]
        return registro.custo_estimado(
            linha.get("provedor"), linha.get("modelo"),
            linha.get("tokens_entrada"), linha.get("tokens_saida"),
        )

    df = df.copy()
    df["custo_usd"] = df.apply(estimar, axis=1)
    return df


def _formatar_moeda(valor: float, simbolo: str) -> str:
    """'$ 0' em vez de '$ 0.0000'; 4 casas para valores pequenos de API."""
    texto = f"{valor:,.4f}".rstrip("0").rstrip(".")
    return f"{simbolo} {texto or '0'}"


def _render_metricas_topo(df: pd.DataFrame) -> None:
    """Linha 1: contagens e validade. Linha 2: custo (US$ e R$), tempo e tokens."""
    col_total, col_pend, col_apr, col_rej, col_json = st.columns(5)
    col_total.metric("Total", len(df))
    contagens = df["status_validacao"].value_counts()
    col_pend.metric(ROTULOS_STATUS["pendente"], int(contagens.get("pendente", 0)))
    col_apr.metric(ROTULOS_STATUS["aprovado"], int(contagens.get("aprovado", 0)))
    col_rej.metric(ROTULOS_STATUS["rejeitado"], int(contagens.get("rejeitado", 0)))
    col_json.metric("JSON válido", f"{df['json_valido'].mean():.0%}")

    custo_total = df["custo_usd"].dropna().sum()
    sem_preco = int(df["custo_usd"].isna().sum())
    col_usd, col_brl, col_llm, col_tok, _ = st.columns(5)
    col_usd.metric("💵 Custo (US$)", _formatar_moeda(custo_total, "$"))
    col_brl.metric("💰 Custo (R$)", _formatar_moeda(custo_total * CAMBIO_USD_BRL, "R$"))
    media_llm = df["duracao_llm_s"].dropna().mean()
    col_llm.metric("⏱️ LLM médio/doc", f"{media_llm:.1f}s" if pd.notna(media_llm) else "—")
    tokens = df[["tokens_entrada", "tokens_saida"]].sum(numeric_only=True).sum()
    col_tok.metric("🔡 Tokens (total)", f"{int(tokens):,}".replace(",", "."))

    legenda = f"Câmbio configurado: US$ 1 = R$ {CAMBIO_USD_BRL:.2f} (`config.CAMBIO_USD_BRL`)."
    if sem_preco:
        legenda += (
            f" ⚠️ {sem_preco} extração(ões) **sem preço cadastrado** para o modelo "
            "ficam fora do custo (cadastre em `registro.PRECO_POR_MILHAO`)."
        )
    st.caption(legenda)


def _render_medias_condicao(df: pd.DataFrame) -> None:
    """Tempo/tokens/custo médios por condição (RAG on/off) — espelha a métrica
    secundária da avaliação, agora sobre o histórico filtrado."""
    medias = (
        df.assign(condicao=df["use_rag"].map({1: "🔗 COM RAG", 0: "⛔ SEM RAG"}))
        .groupby("condicao")[["duracao_llm_s", "tokens_entrada", "tokens_saida", "custo_usd"]]
        .mean(numeric_only=True)
        .round({"duracao_llm_s": 1, "tokens_entrada": 1, "tokens_saida": 1, "custo_usd": 6})
    )
    if medias.empty:
        return
    st.markdown("**Médias por condição** (tempo do LLM em segundos; custo em US$/doc):")
    st.dataframe(medias, width="stretch")


def _render_graficos(df: pd.DataFrame, escolhido: str) -> None:
    """Volume por experimento e por dia, lado a lado."""
    col_exp, col_dia = st.columns(2)
    if escolhido == "todos" and df["experimento"].nunique() > 1:
        with col_exp:
            st.markdown("**Extrações por experimento:**")
            st.bar_chart(df["experimento"].value_counts())
    por_dia = pd.to_datetime(df["criado_em"], format="mixed").dt.date.value_counts().sort_index()
    if len(por_dia) > 1:
        with col_dia:
            st.markdown("**Extrações por dia:**")
            st.bar_chart(por_dia)


def _render_extracoes() -> None:
    linhas = registro.carregar_extracoes()
    if not linhas:
        st.info(
            "Nenhuma extração registrada ainda. Use a página **Validação** ou "
            "rode uma avaliação — toda extração entra aqui automaticamente."
        )
        return

    df = _com_custo(pd.DataFrame(linhas))

    # Filtro por experimento, com rótulos amigáveis ('cli' fora das opções).
    presentes = [
        e for e in sorted(df["experimento"].dropna().unique())
        if e not in EXPERIMENTOS_OCULTOS
    ]
    escolhido = st.selectbox(
        "Experimento",
        ["todos"] + presentes,
        index=0,
        format_func=lambda e: ROTULOS_EXPERIMENTO.get(e, e),
    )
    if escolhido != "todos":
        df = df[df["experimento"] == escolhido]

    _render_metricas_topo(df)
    st.divider()
    _render_medias_condicao(df)
    _render_graficos(df, escolhido)

    with st.expander(f"📋 Extrações recentes ({min(len(df), 200)} de {len(df)})"):
        st.dataframe(
            df[COLUNAS_TABELA].head(200),
            width="stretch",
            hide_index=True,
        )


# ---------------------------------------------------------------------------
# Aba 2 — Resultados das avaliações (resultados/)
# ---------------------------------------------------------------------------


def _render_avaliacoes() -> None:
    if not DIR_RESULTADOS.exists():
        st.info("Nenhuma avaliação executada ainda (pasta `resultados/` vazia).")
        return

    # Tabelas Markdown (geradas pelo harness SROIE — prontas para o relatório).
    markdowns = sorted(DIR_RESULTADOS.glob("*.md"))
    graficos = sorted(DIR_RESULTADOS.glob("*.png"))
    csvs = sorted(DIR_RESULTADOS.glob("*.csv"))

    if not (markdowns or graficos or csvs):
        st.info(
            "Nenhum resultado em `resultados/`. Rode "
            "`python src/experimentos/avaliacao_sroie.py --recriar`."
        )
        return

    for md in markdowns:
        st.markdown(md.read_text(encoding="utf-8"))
        st.divider()

    if graficos:
        st.markdown("**Gráficos:**")
        for png in graficos:
            st.image(str(png), caption=png.name, width="stretch")

    if csvs:
        with st.expander("⬇️ Dados brutos (CSV)"):
            for arquivo in csvs:
                st.download_button(
                    label=arquivo.name,
                    data=arquivo.read_bytes(),
                    file_name=arquivo.name,
                    mime="text/csv",
                    key=f"dl_{arquivo.name}",
                )


def render() -> None:
    """Desenha o dashboard (somente leitura), em abas."""
    render_hero()
    aba_extracoes, aba_avaliacoes = st.tabs(
        ["🗃️ Extrações", "🧪 Avaliações: baseline vs RAG"]
    )
    with aba_extracoes:
        _render_extracoes()
    with aba_avaliacoes:
        _render_avaliacoes()
