"""
M4 (web) — Página de Validação (orquestração).
===============================================
Fluxo da tela de validação humana (Objetivo 3 + Objetivo 4 ao vivo): upload de
UM documento por vez → extração PAREADA (baseline sem RAG e com RAG, sobre o
MESMO texto OCR) → comparação lado a lado (somente leitura, com divergências
destacadas) → revisão no formulário SEMPRE da versão COM RAG (regra do produto;
o baseline é só referência) → aprovar/corrigir (a COM RAG vira 'aprovado'; o
baseline, 'rejeitado') ou descartar (as duas viram 'rejeitado'). Enquanto há um
documento em revisão, o upload fica travado — termine a revisão para enviar o
próximo. Não desenha widgets direto (isso é de `ui_componentes`) nem aplica
regra de negócio (isso é de `servico_nota`) — só amarra as peças e cuida do
controle de fluxo (`st.spinner`, `st.rerun`).

Os campos do formulário são DINÂMICOS: vêm de `campos.py` e montam o schema via
`schema_dinamico.construir_modelo` — o mesmo schema alimenta o prompt (no
pipeline) e a validação da revisão.
"""

import streamlit as st
from pydantic import ValidationError

from nucleo import campos as campos_mod
from nucleo import registro
from frontend import servico_nota
from frontend import ui_componentes
from frontend import ui_estado
from nucleo.schema_dinamico import construir_modelo

MSG_APROVADA = "✅ Documento aprovado e gravado na base."
MSG_CORRIGIDA = "💾 Correção validada e gravada na base."


def _rejeitar_outras(resultados: dict, condicao_aprovada: str) -> None:
    """Marca como 'rejeitado' a(s) condição(ões) NÃO aprovada(s) — a decisão
    humana fica completa no banco de resultados: uma aprovada, a outra não."""
    for condicao, resultado in resultados.items():
        if condicao != condicao_aprovada:
            servico_nota.descartar(resultado.registro_id)


def _descartar_tudo(resultados: dict) -> None:
    """Descarte total: as duas condições viram 'rejeitado'."""
    for resultado in resultados.values():
        servico_nota.descartar(resultado.registro_id)


def _encerrar_e_recarregar(resultados: dict) -> None:
    """Descarta tudo, limpa a sessão e recarrega (caminho comum dos botões)."""
    _descartar_tudo(resultados)
    ui_estado.limpar_extracao()
    st.rerun()


def render() -> None:
    """Desenha e orquestra a página de validação.

    Resolve a base pela CONFIGURAÇÃO de campos: cada config tem sua própria
    coleção Chroma (campos.nome_colecao_para). Assim os aprovados de uma
    configuração não se misturam com os de outra nem com a avaliação SROIE."""
    cfg = campos_mod.carregar_config()
    Modelo = construir_modelo(cfg)
    versao = campos_mod.versao_dos_campos(cfg)
    nome_colecao = campos_mod.nome_colecao_para(cfg)  # notas_v<versao>
    banco = ui_estado.carregar_banco(nome_colecao)

    selecoes = ui_componentes.render_sidebar_extracao(banco.contar(), nome_colecao, versao)

    ui_componentes.render_hero_validacao()
    ui_componentes.render_flash(ui_estado.pop_flash())

    resultados = ui_estado.get_resultados()

    # --- Upload + extração pareada (UM documento por vez) ---
    # Com um documento em revisão, o uploader some: aprove/descarte primeiro.
    if resultados is None:
        enviado = ui_componentes.render_uploader()
        if enviado is not None and ui_componentes.render_botao_extrair():
            try:
                with st.spinner("Rodando OCR + LLM nas duas condições (sem/com RAG)…"):
                    resultados = servico_nota.executar_extracao_pareada(
                        enviado.getvalue(),
                        enviado.name,
                        banco,
                        provedor=selecoes.provedor,
                        modelo=selecoes.modelo,
                        modelo_schema=Modelo,  # schema DINÂMICO (campos configuráveis)
                        versao_campos=versao,
                        idioma_ocr=cfg.get("idioma_ocr"),
                    )
                ui_estado.set_resultados(resultados, enviado.getvalue())
                # Semeia o formulário com a condição de revisão (COM RAG) ANTES
                # de o formulário instanciar os widgets (gotcha do Streamlit).
                condicao = ui_estado.condicao_revisao(resultados)
                if condicao:
                    ui_estado.prefill_formulario(cfg, resultados[condicao].nota)
                st.rerun()
            except Exception as erro:  # Ollama offline, chave Gemini ausente, etc.
                st.error(f"Falha na extração: {erro}")
        if ui_estado.get_resultados() is None:
            ui_componentes.render_empty_state()
            return
    else:
        st.info(
            "📄 **Documento em revisão** — aprove, corrija ou descarte para "
            "enviar o próximo (um por vez)."
        )

    resultados = ui_estado.get_resultados()
    condicao = ui_estado.condicao_revisao(resultados)

    col_img, col_form = st.columns(2)
    with col_img:
        ui_componentes.render_coluna_imagem(
            ui_estado.get_imagem(), resultados["sem_rag"].texto_ocr
        )

    with col_form:
        # As duas condições falharam: nada para validar.
        if condicao is None:
            ui_componentes.render_falha_extracao(resultados["com_rag"])
            if ui_componentes.render_botao_descartar():
                _encerrar_e_recarregar(resultados)
            return

        # Comparação somente leitura (o baseline é referência; divergências 🟡).
        ui_componentes.render_comparacao(resultados, cfg, condicao)

        resultado = resultados[condicao]
        st.subheader(f"📝 Revisão — {ui_componentes.ROTULOS_CONDICAO[condicao]}")
        ui_componentes.render_status_extracao(resultado)

        aprovar, corrigir, itens_edit = ui_componentes.render_formulario(
            cfg, ui_estado.get_itens_form()
        )
        if aprovar or corrigir:
            valores = ui_estado.ler_valores_campos(cfg)
            dados = servico_nota.montar_dados(cfg, valores, itens_edit)
            try:
                servico_nota.validar_e_gravar(
                    banco,
                    Modelo,
                    resultado.texto_ocr,
                    dados,
                    cfg=cfg,
                    imagem_bytes=ui_estado.get_imagem(),
                    registro_id=resultado.registro_id,
                )
            except ValidationError as erro:
                # Inválido: exibe o erro e NÃO grava nem dá rerun.
                ui_componentes.mostrar_erro_formulario(erro)
            else:
                _rejeitar_outras(resultados, condicao)
                ui_estado.set_flash(MSG_APROVADA if aprovar else MSG_CORRIGIDA)
                ui_estado.limpar_extracao()
                st.rerun()

        ui_componentes.render_json_bruto(resultado.nota)

        if ui_componentes.render_botao_descartar():
            _encerrar_e_recarregar(resultados)

    # --- Contexto histórico (mesma visão do Dashboard) ---
    ui_componentes.render_medias_condicao(registro.medias_por_condicao())
