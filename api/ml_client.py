import time
import random
import requests

BASE_URL = "https://api.mercadolivre.com"


class MLClient:
    def __init__(self, access_token: str, user_id: str):
        self.access_token = access_token
        self.user_id = user_id
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {access_token}"})

    def _human_delay(self):
        time.sleep(random.uniform(0.3, 1.2))

    def _get(self, path: str, params: dict = None) -> dict:
        self._human_delay()
        resp = self._session.get(f"{BASE_URL}{path}", params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, json_body: dict) -> dict:
        self._human_delay()
        resp = self._session.put(f"{BASE_URL}{path}", json=json_body, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json_body: dict) -> dict:
        self._human_delay()
        resp = self._session.post(f"{BASE_URL}{path}", json=json_body, timeout=20)
        resp.raise_for_status()
        return resp.json()

    # --- Anúncios ---

    def get_user_items(self) -> list[str]:
        """Retorna todos os IDs de anúncios ativos do usuário."""
        item_ids = []
        offset = 0
        limit = 50
        while True:
            data = self._get(
                f"/users/{self.user_id}/items/search",
                params={"status": "active", "offset": offset, "limit": limit},
            )
            results = data.get("results", [])
            item_ids.extend(results)
            paging = data.get("paging", {})
            if offset + limit >= paging.get("total", 0):
                break
            offset += limit
        return item_ids

    def get_item_details(self, item_id: str) -> dict:
        """Retorna detalhes de um anúncio incluindo variações e seller_custom_field."""
        return self._get(f"/items/{item_id}")

    def get_items_batch(self, item_ids: list[str]) -> list[dict]:
        """Busca até 20 itens por chamada para reduzir requisições."""
        results = []
        for i in range(0, len(item_ids), 20):
            batch = item_ids[i : i + 20]
            data = self._get("/items", params={"ids": ",".join(batch)})
            for entry in data:
                if entry.get("code") == 200:
                    results.append(entry["body"])
        return results

    # --- Promoções / Ofertas Relâmpago ---

    def get_item_promotions(self, item_id: str) -> list[dict]:
        """Lista promoções disponíveis para um anúncio."""
        try:
            data = self._get(f"/seller-promotions/items/{item_id}/promotions")
            return data if isinstance(data, list) else data.get("results", [])
        except requests.HTTPError:
            return []

    def get_available_deals(self) -> list[dict]:
        """Lista ofertas relâmpago disponíveis para o vendedor."""
        try:
            data = self._get(
                f"/seller-promotions/users/{self.user_id}/promotions",
                params={"status": "candidate,started", "promotion_type": "price_discount"},
            )
            return data if isinstance(data, list) else data.get("results", [])
        except requests.HTTPError:
            return []

    def get_deal_items(self, promotion_id: str) -> list[dict]:
        """Retorna os itens de uma promoção específica com preço sugerido pelo ML."""
        try:
            data = self._get(f"/seller-promotions/{promotion_id}/items")
            return data if isinstance(data, list) else data.get("results", [])
        except requests.HTTPError:
            return []

    def set_deal_price(self, promotion_id: str, item_id: str, price: float) -> dict:
        """Aplica preço de oferta relâmpago para um item em uma promoção."""
        return self._put(
            f"/seller-promotions/{promotion_id}/items/{item_id}",
            {"price": round(price, 2)},
        )

    # --- Campanhas ---

    def get_campaigns(self) -> list[dict]:
        """Lista campanhas de publicidade disponíveis."""
        try:
            data = self._get(
                f"/advertising/product-ads/v1/campaigns",
                params={"user_id": self.user_id},
            )
            return data if isinstance(data, list) else data.get("results", [])
        except requests.HTTPError:
            return []

    def get_promotion_metrics(self, promotion_id: str) -> dict:
        """Métricas de uma promoção: visibilidade estimada, receita, etc."""
        try:
            return self._get(f"/seller-promotions/{promotion_id}/metrics")
        except requests.HTTPError:
            return {}
