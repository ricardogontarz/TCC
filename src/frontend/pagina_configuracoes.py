"""
M4 (web) — Página de Configurações de campos (orquestração).
============================================================
Permite ADICIONAR / REMOVER os campos que o sistema espera extrair, sem mexer
no código. Orquestra o domínio de campos (`campos.py`: carregar/salvar/validar)
com os widgets de view (`ui_componentes`) e o controle de fluxo (`st.rerun`).

Escopo: afeta SÓ o caminho de produção (app/CLI). A avaliação SROIE segue no
schema FIXO (ReciboSROIE) — o experimento controlado do TCC.
"""

import streamlit as st

from nucleo import campos as campos_mod
from frontend import ui_componentes


def render() -> None:
    """Desenha e orquestra a página de configurações de campos."""
    cfg = campos_mod.carregar_config()

    ui_componentes.render_hero_config()
    ui_componentes.render_info_config()

    # Versão atual dos campos: muda sempre que algum campo muda. Identifica a
    # base e os resultados, sem afetar versões anteriores.
    versao = campos_mod.versao_dos_campos(cfg)
    st.info(
        f"📌 **Versão dos campos: v{versao}** — alterar qualquer campo gera uma nova "
        "versão (com base e resultados próprios). Voltar a uma configuração anterior "
        "reusa a versão dela. Resultados ficam separados por modelo + versão."
    )

    # --- Campos atuais (listar + remover) ---
    st.subheader("Campos atuais")
    if not cfg["campos"]:
        st.warning("Nenhum campo configurado. Adicione ao menos um abaixo.")
    for campo in cfg["campos"]:
        if ui_componentes.render_campo_row(campo):
            cfg["campos"] = [c for c in cfg["campos"] if c["chave"] != campo["chave"]]
            campos_mod.salvar_config(cfg)
            st.rerun()

    # --- Adicionar campo escalar ---
    st.divider()
    submetido, rotulo, tipo = ui_componentes.render_form_adicionar()
    if submetido:
        chave = campos_mod.slugificar(rotulo)
        erro = campos_mod.validar_novo_campo(cfg, rotulo, chave, tipo)
        if erro:
            st.error(erro)
        else:
            cfg["campos"].append({"chave": chave, "rotulo": rotulo.strip(), "tipo": tipo})
            campos_mod.salvar_config(cfg)
            st.success(f"Campo '{rotulo.strip()}' adicionado (chave: {chave}).")
            st.rerun()

    # --- Incluir lista de itens? ---
    st.divider()
    incluir = ui_componentes.render_toggle_itens(cfg.get("incluir_itens", True))
    if incluir != cfg.get("incluir_itens", True):
        cfg["incluir_itens"] = incluir
        campos_mod.salvar_config(cfg)
        st.rerun()

    # --- Campos dos itens/materiais (só fazem sentido se incluir_itens) ---
    if cfg.get("incluir_itens", True):
        st.subheader("Campos dos itens (materiais)")
        st.caption("Colunas de cada item da nota — refletem no prompt e na tabela de revisão.")
        if not cfg.get("campos_item"):
            st.warning("Nenhum campo de item. Adicione ao menos um abaixo.")
        for campo in cfg.get("campos_item", []):
            if ui_componentes.render_campo_item_row(campo):
                cfg["campos_item"] = [
                    c for c in cfg["campos_item"] if c["chave"] != campo["chave"]
                ]
                campos_mod.salvar_config(cfg)
                st.rerun()

        submetido_i, rotulo_i, tipo_i = ui_componentes.render_form_adicionar_item()
        if submetido_i:
            chave_i = campos_mod.slugificar(rotulo_i)
            erro_i = campos_mod.validar_novo_campo_item(cfg, rotulo_i, chave_i, tipo_i)
            if erro_i:
                st.error(erro_i)
            else:
                cfg.setdefault("campos_item", []).append(
                    {"chave": chave_i, "rotulo": rotulo_i.strip(), "tipo": tipo_i}
                )
                campos_mod.salvar_config(cfg)
                st.success(f"Campo de item '{rotulo_i.strip()}' adicionado (chave: {chave_i}).")
                st.rerun()

    # --- Restaurar padrão (= campos do gabarito SROIE) ---
    st.divider()
    if ui_componentes.render_botao_restaurar():
        campos_mod.salvar_config(campos_mod.CONFIG_PADRAO)
        st.rerun()

