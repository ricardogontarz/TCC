"""
M4 (web) — Componentes de view (camada de apresentação).
========================================================
Responsabilidade ÚNICA: desenhar a tela com widgets do Streamlit. Estas
funções NÃO contêm regra de negócio — não escrevem no banco, não validam com
Pydantic e não chamam `st.rerun`. Elas apenas desenham e DEVOLVEM ao
controlador da página o que o usuário escolheu/fez (seleções e cliques).

De `ui_estado` importamos só as CONSTANTES de key dos widgets (a view declara
`key=...`, mas o namespace de sessão é de propriedade do estado — fonte única
dos nomes). De `campos`/`config` lemos apenas constantes/derivações de exibição.
Sem `st.*` em nível de módulo — todo desenho vive dentro de uma função.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import streamlit as st

from nucleo import campos as campos_mod
from nucleo import config
from frontend import ui_estado
from nucleo.pipeline import ResultadoExtracao


@dataclass(frozen=True)
class SelecoesSidebar:
    """Escolhas do operador na sidebar de extração, devolvidas à página."""

    provedor: str  # "ollama" | "gemini"
    modelo: str    # derivado do provedor (config) — não editável pelo usuário


# ---------------------------------------------------------------------------
# Helpers de apresentação.
# ---------------------------------------------------------------------------
def _esc(texto) -> str:
    """Escapa texto para injetar com segurança no HTML dos cartões/badges."""
    return str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _rotulo_campo(campo: dict) -> str:
    """Rótulo do widget com uma dica de formato conforme o tipo."""
    dica = {"numero": " (número)", "data": " (aaaa-mm-dd)"}.get(campo["tipo"], "")
    return f"{campo['rotulo']}{dica}"


# ---------------------------------------------------------------------------
# Componentes — página de Validação.
# ---------------------------------------------------------------------------
def render_sidebar_extracao(
    banco_count: int, nome_colecao: str = "", versao_campos: Optional[int] = None
) -> SelecoesSidebar:
    """Desenha a configuração da extração e DEVOLVE as seleções do usuário.

    Recebe a contagem da base, o nome da coleção ativa e a versão dos campos já
    resolvidos — para a view não tocar no domínio. O modelo é DETERMINADO pelo
    provedor (fonte única: config.py) e exibido somente leitura."""
    st.sidebar.markdown("### ⚙️ Configuração da extração")
    provedor = st.sidebar.selectbox(
        "Provedor de LLM",
        options=["ollama", "gemini"],
        index=0 if config.PROVEDOR_LLM == "ollama" else 1,
        help="ollama = modelo local, grátis e offline. gemini = API do Google.",
    )
    # O modelo é DETERMINADO pelo provedor (fonte única: config.py), só leitura.
    modelo = config.MODELO_OLLAMA if provedor == "ollama" else config.MODELO_LLM
    st.sidebar.text_input("Modelo (definido pelo provedor)", value=modelo, disabled=True)
    st.sidebar.caption(
        "Cada extração roda nas **duas condições** — baseline (sem RAG) e com "
        "RAG — sobre o mesmo OCR, e você escolhe qual resultado validar."
    )

    emoji_provedor = "🖥️" if provedor == "ollama" else "☁️"
    st.sidebar.markdown(
        '<div style="margin-top:.6rem">'
        f'<span class="badge badge-info">{emoji_provedor} {_esc(provedor)}</span>'
        f'<span class="badge badge-muted">🧠 {_esc(modelo)}</span>'
        '<span class="badge badge-ok">⚖️ baseline vs RAG</span></div>',
        unsafe_allow_html=True,
    )
    st.sidebar.divider()
    if versao_campos is not None:
        st.sidebar.metric("Versão dos campos", f"v{versao_campos}")
    st.sidebar.metric("Pares validados na base", banco_count)
    if nome_colecao:
        st.sidebar.caption(f"Coleção ativa (por versão): `{nome_colecao}`")
    st.sidebar.caption("A base cresce a cada documento aprovado (realimentação — Obj 3).")

    return SelecoesSidebar(provedor=provedor, modelo=modelo)


def render_hero_validacao() -> None:
    """Cabeçalho da página de validação."""
    st.markdown(
        """
        <div class="app-hero">
            <h1>🧾 Validação de Documentos — RAG + OCR</h1>
            <p>Upload → OCR + LLM extraem nas <b>duas condições</b> (baseline e RAG)
            → você compara, revisa no <b>formulário</b> e <b>aprova</b>, <b>corrige</b>
            ou <b>descarta</b>. Só dados válidos entram na base.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_flash(mensagem: Optional[str]) -> None:
    """Mostra a mensagem de sucesso pendente do run anterior (se houver)."""
    if mensagem:
        st.success(mensagem)


def render_uploader() -> Optional["st.runtime.uploaded_file_manager.UploadedFile"]:
    """File uploader do documento (PNG/JPG). Devolve o arquivo enviado ou None."""
    enviado = st.file_uploader("Imagem do documento", type=["png", "jpg", "jpeg"])
    st.caption("Por ora aceitamos imagens (PNG/JPG). Suporte a PDF é extensão futura.")
    return enviado


def render_botao_extrair() -> bool:
    """Botão primário de extração. Devolve True no clique."""
    return st.button("🚀 Extrair", type="primary")


def render_empty_state() -> None:
    """Orienta o operador, passo a passo, enquanto não há nota carregada."""
    st.markdown(
        """
        <div class="empty-state">
            <span class="emoji">📤</span>
            <h3>Nenhum documento carregado ainda</h3>
            <div>Envie uma imagem para começar a validação (um documento por vez).</div>
            <ol>
                <li>Escolha o <b>provedor</b> na barra lateral.</li>
                <li>Faça o <b>upload</b> da imagem do documento (PNG ou JPG).</li>
                <li>Clique em <b>🚀 Extrair</b>: o sistema roda <b>sem RAG e com RAG</b>
                    sobre o mesmo OCR e mostra os dois resultados lado a lado.</li>
                <li>Revise a versão <b>COM RAG</b> no formulário (o baseline é só
                    referência) e <b>aprove</b>, <b>corrija</b> ou <b>descarte</b>.</li>
            </ol>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_coluna_imagem(imagem: Optional[bytes], texto_ocr: str) -> None:
    """Coluna esquerda: a imagem da nota + o texto bruto do OCR."""
    st.subheader("📎 Nota original")
    if imagem:
        st.image(imagem, width="stretch")
    with st.expander("🔍 Texto bruto do OCR"):
        st.text(texto_ocr or "(OCR vazio)")


def render_status_extracao(resultado: ResultadoExtracao) -> None:
    """Badge de status: validou na 1ª tentativa ou só na 2ª (1 retry)."""
    if resultado.valido_primeira:
        st.markdown(
            '<span class="badge badge-ok">✅ Validou na 1ª tentativa</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="badge badge-warn">🔁 Validou na 2ª tentativa</span>',
            unsafe_allow_html=True,
        )


ROTULOS_CONDICAO = {
    "sem_rag": "⛔ SEM RAG (baseline)",
    "com_rag": "🔗 COM RAG",
}


def _campos_divergentes(resultados: dict, cfg: dict) -> set:
    """Chaves de campo em que as duas condições discordam (para destacar na
    comparação). Se alguma condição falhou, nada é destacado."""
    sem, com = resultados.get("sem_rag"), resultados.get("com_rag")
    if not sem or not com or sem.nota is None or com.nota is None:
        return set()
    dados_sem, dados_com = sem.nota.model_dump(), com.nota.model_dump()
    return {
        campo["chave"]
        for campo in cfg["campos"]
        if dados_sem.get(campo["chave"]) != dados_com.get(campo["chave"])
    }


def _render_cartao_condicao(
    condicao: str,
    resultado: ResultadoExtracao,
    cfg: dict,
    em_revisao: bool,
    divergentes: set,
) -> None:
    """Um cartão da comparação: rótulo da condição, instrumentação e os valores
    por campo (campos onde as condições divergem ganham destaque)."""
    papel = (
        '<span class="badge badge-ok">📝 vai para a revisão</span>'
        if em_revisao
        else '<span class="badge badge-muted">👁️ somente referência</span>'
    )
    st.markdown(
        f"**{ROTULOS_CONDICAO[condicao]}** {papel}", unsafe_allow_html=True
    )
    detalhes = []
    if condicao == "com_rag":
        detalhes.append(
            f"📚 {resultado.k_exemplos} exemplo(s) recuperado(s)"
            if resultado.k_exemplos
            else "base vazia — operou como LLM puro (cold start)"
        )
    if resultado.duracao_llm_s is not None:
        detalhes.append(f"⏱️ LLM {resultado.duracao_llm_s:.1f}s")
    if resultado.tokens_entrada is not None:
        detalhes.append(f"🔡 {resultado.tokens_entrada} tokens de entrada")
    if detalhes:
        st.caption(" · ".join(detalhes))

    if resultado.nota is None:
        st.error("Falhou: o LLM não devolveu JSON válido após 2 tentativas.")
        if resultado.erro:
            with st.expander("Detalhe do erro"):
                st.code(resultado.erro)
        return

    dados = resultado.nota.model_dump()
    for campo in cfg["campos"]:
        valor = dados.get(campo["chave"])
        exibido = "—" if valor is None else _esc(valor)
        classe = "badge-warn" if campo["chave"] in divergentes else "badge-muted"
        st.markdown(
            f'<div class="campo-comparacao"><span class="badge {classe}">'
            f'{_esc(campo["rotulo"])}</span> {exibido}</div>',
            unsafe_allow_html=True,
        )


def render_comparacao(resultados: dict, cfg: dict, condicao_revisao: Optional[str]) -> None:
    """Comparação lado a lado das duas condições (mesmo OCR). Campos em que as
    condições divergem aparecem destacados (🟡). Somente leitura: a revisão é
    SEMPRE a da condição `condicao_revisao` (regra do produto: COM RAG)."""
    st.subheader("⚖️ Baseline vs RAG (mesmo OCR)")
    divergentes = _campos_divergentes(resultados, cfg)
    if divergentes:
        rotulos = [c["rotulo"] for c in cfg["campos"] if c["chave"] in divergentes]
        st.caption(f"🟡 As condições divergem em: **{', '.join(rotulos)}**.")
    colunas = st.columns(2)
    for coluna, condicao in zip(colunas, ("sem_rag", "com_rag")):
        with coluna.container(border=True):
            _render_cartao_condicao(
                condicao,
                resultados[condicao],
                cfg,
                em_revisao=(condicao == condicao_revisao),
                divergentes=divergentes,
            )


def render_medias_condicao(medias: List[dict]) -> None:
    """Tabela de médias por condição (mesma visão do Dashboard), como contexto
    histórico ao lado da extração corrente."""
    if not medias:
        return
    with st.expander("📈 Médias históricas por condição (tempo do LLM em segundos)"):
        st.dataframe(medias, width="stretch", hide_index=True)
        st.caption(
            "Sobre todas as extrações registradas (app, CLI e avaliações) — "
            "a mesma tabela da página Dashboard."
        )


def render_falha_extracao(resultado: ResultadoExtracao) -> None:
    """Estado de falha: o LLM não devolveu JSON válido após 2 tentativas."""
    st.markdown(
        '<span class="badge badge-warn">⚠️ Extração falhou</span>',
        unsafe_allow_html=True,
    )
    st.error(
        "O LLM não devolveu um JSON válido após 2 tentativas. "
        "Sem extração para validar."
    )
    if resultado.erro:
        st.code(resultado.erro)


def render_formulario(
    cfg: dict, itens_iniciais: List[dict]
) -> Tuple[bool, bool, Optional[List[dict]]]:
    """Formulário de revisão: um campo por configuração + tabela de itens.
    Devolve (aprovar, corrigir, itens_edit).

    Os text_inputs usam `key=PREFIXO_CAMPO + chave` — as MESMAS keys que o
    estado pré-preenche no handler do Extrair (antes deste formulário rodar).
    Esta função apenas declara os widgets; NUNCA escreve essas keys."""
    itens_edit: Optional[List[dict]] = None
    with st.form("form_revisao"):
        for campo in cfg["campos"]:
            st.text_input(_rotulo_campo(campo), key=ui_estado.PREFIXO_CAMPO + campo["chave"])

        if cfg.get("incluir_itens", True):
            st.markdown("**Itens da nota**")
            # Colunas DINÂMICAS: uma por campo de item configurado (cfg["campos_item"]).
            column_config = {
                c["chave"]: st.column_config.TextColumn(c["rotulo"])
                for c in cfg.get("campos_item", [])
            }
            itens_edit = st.data_editor(
                itens_iniciais,
                num_rows="dynamic",
                width="stretch",
                key=ui_estado.CHAVE_EDITOR_ITENS,
                column_config=column_config,
            )

        c1, c2 = st.columns(2)
        aprovar = c1.form_submit_button("✅ Aprovar", type="primary", width="stretch")
        corrigir = c2.form_submit_button("💾 Salvar correção", width="stretch")

    return aprovar, corrigir, itens_edit


def render_json_bruto(nota) -> None:
    """Expander com o JSON extraído (bruto), para conferência."""
    with st.expander("🔎 Ver JSON extraído (bruto)"):
        st.code(nota.model_dump_json(indent=2), language="json")


def render_botao_descartar() -> bool:
    """Botão de descarte. Devolve True no clique."""
    return st.button("🗑️ Descartar", width="stretch")


def mostrar_erro_formulario(erro: Exception) -> None:
    """Exibe a falha de validação do formulário (a exibição é uma preocupação
    de view; quem decide não gravar/não dar rerun é a página)."""
    st.error("Formulário inválido — nada foi gravado. Revise os campos.")
    st.code(str(erro))


# ---------------------------------------------------------------------------
# Componentes — página de Configurações.
# ---------------------------------------------------------------------------
def render_hero_config() -> None:
    """Cabeçalho da página de configurações de campos."""
    st.markdown(
        """
        <div class="app-hero">
            <h1>⚙️ Configurações de campos</h1>
            <p>Defina QUAIS dados o sistema espera extrair das notas. Vale para a
            extração e para o formulário de revisão.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_info_config() -> None:
    """Aviso de escopo: a config afeta só o caminho de produção (app)."""
    st.info(
        "Os campos PADRÃO são os mesmos do ground truth (SROIE: company, address, "
        "date, total — derivados de `nucleo/schema.py`); campos extras podem ser "
        "adicionados por cima. Estas configurações afetam o app/CLI (produção): a "
        "avaliação baseline vs RAG continua usando o schema fixo do gabarito."
    )


def render_campo_row(campo: dict) -> bool:
    """Uma linha da lista de campos (rótulo, chave, tipo) + botão remover.
    Devolve True se o usuário clicou para remover."""
    c1, c2, c3, c4 = st.columns([3, 3, 2, 1])
    c1.markdown(f"**{_esc(campo['rotulo'])}**")
    c2.code(campo["chave"])
    c3.markdown(
        f'<span class="badge badge-info">{campo["tipo"]}</span>',
        unsafe_allow_html=True,
    )
    return c4.button("🗑️", key=f"rm_{campo['chave']}", help="Remover campo")


def render_toggle_itens(valor_atual: bool) -> bool:
    """Checkbox de incluir a lista de itens. Devolve o valor escolhido."""
    return st.checkbox(
        "Incluir a lista de itens da nota (descrição, qtd, valor unit.)",
        value=valor_atual,
    )


def render_form_adicionar() -> Tuple[bool, str, str]:
    """Formulário de adicionar campo. Devolve (submetido, rotulo, tipo).
    Mostra um preview da chave gerada (slug) enquanto o usuário digita."""
    st.subheader("Adicionar campo")
    with st.form("add_campo"):
        rotulo = st.text_input("Rótulo (ex.: Inscrição Estadual)")
        tipo = st.selectbox("Tipo", list(campos_mod.TIPOS_VALIDOS))
        if rotulo.strip():
            st.caption(f"Chave gerada: `{campos_mod.slugificar(rotulo)}`")
        submetido = st.form_submit_button("➕ Adicionar campo", type="primary")
    return submetido, rotulo, tipo


def render_campo_item_row(campo: dict) -> bool:
    """Uma linha da lista de campos do ITEM (material) + botão remover. Usa um
    prefixo de key próprio ('rmi_') para não colidir com os campos escalares."""
    c1, c2, c3, c4 = st.columns([3, 3, 2, 1])
    c1.markdown(f"**{_esc(campo['rotulo'])}**")
    c2.code(campo["chave"])
    c3.markdown(
        f'<span class="badge badge-info">{campo["tipo"]}</span>',
        unsafe_allow_html=True,
    )
    return c4.button("🗑️", key=f"rmi_{campo['chave']}", help="Remover campo do item")


def render_form_adicionar_item() -> Tuple[bool, str, str]:
    """Formulário de adicionar campo de ITEM. Devolve (submetido, rotulo, tipo).
    Usa labels/keys próprios para não colidir com o formulário dos escalares."""
    st.subheader("Adicionar campo de item")
    with st.form("add_campo_item"):
        rotulo = st.text_input("Rótulo do campo de item (ex.: Unidade, NCM)")
        tipo = st.selectbox("Tipo do campo de item", list(campos_mod.TIPOS_VALIDOS))
        if rotulo.strip():
            st.caption(f"Chave gerada: `{campos_mod.slugificar(rotulo)}`")
        submetido = st.form_submit_button("➕ Adicionar campo de item", type="primary")
    return submetido, rotulo, tipo


def render_botao_restaurar() -> bool:
    """Botão de restaurar os campos padrão (= gabarito SROIE). True no clique."""
    return st.button("↩️ Restaurar campos padrão (gabarito SROIE)")


