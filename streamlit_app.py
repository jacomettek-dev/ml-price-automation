import streamlit as st
from api.ml_client import MLClient
from auth.ml_auth import get_auth_url, exchange_code
from core import sku_cache
from core.price_engine import build_decisions, decisions_to_df
from core.campaign_analyzer import analyze_campaigns
from data.spreadsheet_reader import read_price_sheet

st.set_page_config(
    page_title="ML Price Automation — SofistiCasa",
    page_icon="🛒",
    layout="wide",
)

for key, default in [
    ("client", None),
    ("tokens", {}),
    ("decisions", []),
    ("price_df", None),
    ("campaigns_df", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# Detecta código OAuth retornado pelo ML na URL
code_from_url = st.query_params.get("code", "")

tab_config, tab_offers, tab_campaigns = st.tabs(
    ["⚙ Configuração", "💲 Ofertas Relâmpago", "📊 Campanhas"]
)

# ─── ABA CONFIGURAÇÃO ────────────────────────────────────────────────────────
with tab_config:
    st.header("Configuração do Mercado Livre")

    if st.session_state.client:
        st.success(f"✅ Conectado | User ID: {st.session_state.tokens.get('user_id', '')}")
        if st.button("Desconectar"):
            st.session_state.client = None
            st.session_state.tokens = {}
            st.rerun()
    else:
        if code_from_url:
            st.info(
                f"Código de autorização detectado na URL! "
                f"Cole suas credenciais abaixo e clique em **Confirmar autenticação**."
            )

        col1, col2 = st.columns(2)
        with col1:
            client_id = st.text_input("Client ID", key="client_id")
        with col2:
            client_secret = st.text_input("Client Secret", type="password", key="client_secret")

        app_url = st.text_input(
            "URL do app (registre esta como URI de redirecionamento no ML Developers)",
            placeholder="https://seuapp.streamlit.app",
            key="app_url",
        )

        if client_id and app_url:
            auth_url = get_auth_url(client_id, app_url)
            st.markdown(
                "**Passo 1 —** Registre a URL acima no "
                "[ML Developers](https://developers.mercadolivre.com.br) "
                "como URI de redirecionamento.\n\n"
                "**Passo 2 —** Clique em **Autorizar** (abre nova aba). "
                "Após autorizar, o ML redireciona para sua URL com `?code=...` na barra de endereço. "
                "Copie o valor do `code` e cole no campo abaixo."
            )
            st.link_button("🔑 Autorizar no Mercado Livre", auth_url)

        code = st.text_input(
            "Código de autorização (code=...)",
            value=code_from_url,
            placeholder="TG-abc123...",
            key="auth_code",
        )

        if st.button("✅ Confirmar autenticação", type="primary"):
            cid = st.session_state.get("client_id", "").strip()
            csec = st.session_state.get("client_secret", "").strip()
            url = st.session_state.get("app_url", "").strip()
            c = code.strip()

            if not cid or not csec:
                st.error("Preencha Client ID e Client Secret.")
            elif not url:
                st.error("Preencha a URL do app.")
            elif not c:
                st.error("Preencha o código de autorização.")
            else:
                try:
                    with st.spinner("Autenticando..."):
                        token_data = exchange_code(c, cid, csec, url)
                    st.session_state.tokens = token_data
                    st.session_state.client = MLClient(
                        access_token=token_data["access_token"],
                        user_id=str(token_data["user_id"]),
                    )
                    st.query_params.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro na autenticação: {e}")

# ─── ABA OFERTAS RELÂMPAGO ────────────────────────────────────────────────────
with tab_offers:
    st.header("Ofertas Relâmpago — Aplicação de Preços")

    if not st.session_state.client:
        st.warning("⚠ Autentique na aba Configuração primeiro.")
    else:
        col1, col2 = st.columns([2, 3])
        with col1:
            promo_id = st.text_input("ID da Promoção", placeholder="ex: MLB123456", key="promo_id")
        with col2:
            uploaded = st.file_uploader("Planilha de preços (.xlsx)", type=["xlsx"])
            if uploaded:
                try:
                    st.session_state.price_df = read_price_sheet(uploaded)
                    st.success(f"{len(st.session_state.price_df)} SKUs carregados.")
                except Exception as e:
                    st.error(f"Erro ao ler planilha: {e}")

        col_a, col_b, col_c = st.columns(3)

        with col_a:
            if st.button("🔄 Atualizar Cache de SKUs"):
                status = st.empty()
                def _log_cache(m):
                    status.info(m)
                try:
                    with st.spinner("Atualizando cache..."):
                        sku_cache.build_cache(st.session_state.client, on_progress=_log_cache)
                    st.success("Cache atualizado!")
                except Exception as e:
                    st.error(f"Erro: {e}")

        with col_b:
            if st.button("🔍 Buscar Preços ML"):
                if st.session_state.price_df is None:
                    st.error("Carregue a planilha primeiro.")
                elif not promo_id:
                    st.error("Informe o ID da Promoção.")
                else:
                    with st.spinner("Buscando itens da promoção..."):
                        try:
                            deal_items = st.session_state.client.get_deal_items(promo_id)
                            if not deal_items:
                                st.warning("Nenhum item encontrado nesta promoção.")
                            else:
                                if not sku_cache.is_cache_valid():
                                    st.info("Cache desatualizado — atualizando...")
                                    sku_cache.build_cache(st.session_state.client)
                                st.session_state.decisions = build_decisions(
                                    st.session_state.price_df, deal_items, promo_id
                                )
                                n = len(st.session_state.decisions)
                                approved = sum(1 for d in st.session_state.decisions if d.aprovado)
                                st.success(f"{n} itens | ✅ {approved} aprovados | ❌ {n - approved} rejeitados")
                        except Exception as e:
                            st.error(f"Erro ao buscar preços: {e}")

        with col_c:
            if st.button("✅ Aplicar Aprovados", type="primary"):
                approved = [d for d in st.session_state.decisions if d.aprovado]
                if not approved:
                    st.warning("Nenhum item aprovado para aplicar.")
                else:
                    progress_bar = st.progress(0)
                    log_area = st.empty()
                    logs = []
                    for i, d in enumerate(approved):
                        try:
                            st.session_state.client.set_deal_price(
                                d.promotion_id, d.item_id, d.preco_ml_sugerido
                            )
                            logs.append(f"✅ {d.item_id} → R$ {d.preco_ml_sugerido:.2f}")
                        except Exception as e:
                            logs.append(f"❌ {d.item_id}: {e}")
                        progress_bar.progress((i + 1) / len(approved))
                        log_area.text("\n".join(logs[-10:]))
                    st.success("Concluído!")

        if st.session_state.decisions:
            st.dataframe(
                decisions_to_df(st.session_state.decisions),
                use_container_width=True,
                hide_index=True,
            )

# ─── ABA CAMPANHAS ────────────────────────────────────────────────────────────
with tab_campaigns:
    st.header("Análise de Viabilidade de Campanhas")
    st.caption(
        "Score = Visibilidade Estimada ÷ Perda Estimada (R$)   |   Maior score = melhor custo-benefício"
    )

    if not st.session_state.client:
        st.warning("⚠ Autentique na aba Configuração primeiro.")
    else:
        if st.button("📊 Carregar Campanhas"):
            status = st.empty()
            def _log_campaign(m):
                status.info(m)
            with st.spinner("Buscando campanhas..."):
                try:
                    st.session_state.campaigns_df = analyze_campaigns(
                        st.session_state.client, on_progress=_log_campaign
                    )
                except Exception as e:
                    st.error(f"Erro: {e}")

        if st.session_state.campaigns_df is not None:
            df = st.session_state.campaigns_df
            if df.empty:
                st.info("Nenhuma campanha encontrada.")
            else:
                st.success(f"{len(df)} campanhas carregadas.")
                st.dataframe(df, use_container_width=True, hide_index=True)
