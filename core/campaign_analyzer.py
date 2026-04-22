import pandas as pd
from api.ml_client import MLClient


def analyze_campaigns(client: MLClient, on_progress: callable = None) -> pd.DataFrame:
    """
    Busca promoções disponíveis e calcula score de viabilidade.

    Score = visibilidade_estimada / perda_por_item
    Quanto maior o score, mais visibilidade você ganha por real perdido.
    """
    def _progress(msg):
        if on_progress:
            on_progress(msg)

    _progress("Buscando campanhas disponíveis...")
    deals = client.get_available_deals()

    if not deals:
        _progress("Nenhuma campanha encontrada.")
        return pd.DataFrame()

    rows = []
    for deal in deals:
        deal_id = deal.get("id", "")
        name = deal.get("name") or deal.get("promotion_type", deal_id)
        status = deal.get("status", "")
        discount_pct = float(deal.get("discount_meli_amount") or deal.get("discount") or 0)
        start_date = deal.get("start_date", "")
        end_date = deal.get("finish_date") or deal.get("end_date", "")

        _progress(f"Buscando métricas: {name}...")
        metrics = client.get_promotion_metrics(deal_id)
        visibility = float(metrics.get("estimated_impressions") or metrics.get("visibility") or 0)
        revenue_loss = float(metrics.get("total_loss") or metrics.get("revenue_impact") or 0)

        score = round(visibility / revenue_loss, 2) if revenue_loss > 0 else 0.0

        rows.append({
            "ID Promoção": deal_id,
            "Nome": name,
            "Status": status,
            "Desconto (%)": discount_pct,
            "Visibilidade Est.": int(visibility),
            "Perda Estimada (R$)": round(revenue_loss, 2),
            "Score Viabilidade": score,
            "Início": start_date,
            "Fim": end_date,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Score Viabilidade", ascending=False).reset_index(drop=True)
    return df
