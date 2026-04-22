from dataclasses import dataclass, field
import pandas as pd
from core.sku_cache import get_sku_map, get_item_skus_map

TOLERANCE = 2.50  # R$ máximo de diferença para aprovar


@dataclass
class AdPriceDecision:
    item_id: str
    promotion_id: str
    skus: list[str]
    preco_referencia: float       # maior preço sugerido entre os SKUs do anúncio
    preco_ml_sugerido: float      # preço sugerido pelo ML para a promoção
    diferenca: float              # preco_referencia - preco_ml_sugerido
    aprovado: bool


def build_decisions(
    price_df: pd.DataFrame,
    deal_items: list[dict],
    promotion_id: str,
) -> list[AdPriceDecision]:
    """
    Cruza a planilha de preços com os itens de uma promoção ML.

    deal_items: lista de dicts retornados por MLClient.get_deal_items()
      Cada dict deve ter: item_id, suggested_price (preço sugerido pelo ML)
    """
    sku_map = get_sku_map()           # {sku: item_id}
    item_skus = get_item_skus_map()   # {item_id: [sku1, sku2]}

    # índice rápido da planilha: {sku: preco}
    sheet_prices: dict[str, float] = dict(
        zip(price_df["sku"], price_df["preco_sugerido"])
    )

    decisions = []
    for deal in deal_items:
        item_id = deal.get("item_id") or deal.get("id", "")
        ml_price = float(deal.get("suggested_price") or deal.get("price") or 0)
        if not item_id or ml_price == 0:
            continue

        skus_for_item = item_skus.get(item_id, [])
        matched_prices = [
            sheet_prices[sku] for sku in skus_for_item if sku in sheet_prices
        ]

        if not matched_prices:
            continue

        ref_price = max(matched_prices)
        diff = round(ref_price - ml_price, 2)
        approved = diff <= TOLERANCE

        decisions.append(
            AdPriceDecision(
                item_id=item_id,
                promotion_id=promotion_id,
                skus=skus_for_item,
                preco_referencia=ref_price,
                preco_ml_sugerido=ml_price,
                diferenca=diff,
                aprovado=approved,
            )
        )

    decisions.sort(key=lambda d: (not d.aprovado, d.item_id))
    return decisions


def decisions_to_df(decisions: list[AdPriceDecision]) -> pd.DataFrame:
    rows = []
    for d in decisions:
        rows.append({
            "Ad ID": d.item_id,
            "SKUs": ", ".join(d.skus),
            "Preço Ref (R$)": d.preco_referencia,
            "Preço ML (R$)": d.preco_ml_sugerido,
            "Diferença (R$)": d.diferenca,
            "Status": "✅ Aprovado" if d.aprovado else "❌ Rejeitado",
        })
    return pd.DataFrame(rows)
