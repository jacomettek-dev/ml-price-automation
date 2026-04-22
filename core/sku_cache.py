import json
import os
import time
from api.ml_client import MLClient

CACHE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache", "sku_map.json")
CACHE_TTL = 86400  # 24 horas


def _load_raw() -> dict:
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_raw(data: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_cache_valid() -> bool:
    raw = _load_raw()
    ts = raw.get("_timestamp", 0)
    return (time.time() - ts) < CACHE_TTL


def get_sku_map() -> dict[str, str]:
    """Retorna {sku: item_id}. Lê do cache sem verificar TTL."""
    raw = _load_raw()
    return raw.get("map", {})


def get_item_skus_map() -> dict[str, list[str]]:
    """Retorna {item_id: [sku1, sku2, ...]} invertendo o mapa."""
    sku_map = get_sku_map()
    result: dict[str, list[str]] = {}
    for sku, item_id in sku_map.items():
        result.setdefault(item_id, []).append(sku)
    return result


def build_cache(client: MLClient, on_progress: callable = None) -> None:
    """Busca todos os anúncios e variações da conta e salva o cache."""
    def _progress(msg):
        if on_progress:
            on_progress(msg)

    _progress("Buscando lista de anúncios...")
    item_ids = client.get_user_items()
    _progress(f"{len(item_ids)} anúncios encontrados. Buscando variações...")

    sku_map: dict[str, str] = {}
    total = len(item_ids)

    for idx, batch_start in enumerate(range(0, total, 20)):
        batch = item_ids[batch_start : batch_start + 20]
        items = client.get_items_batch(batch)
        for item in items:
            item_id = item.get("id", "")
            _extract_skus(item, item_id, sku_map)
        _progress(f"Processados {min(batch_start + 20, total)}/{total} anúncios...")

    raw = {"_timestamp": time.time(), "map": sku_map}
    _save_raw(raw)
    _progress(f"Cache salvo: {len(sku_map)} SKUs mapeados.")


def _extract_skus(item: dict, item_id: str, sku_map: dict) -> None:
    seller_sku = item.get("seller_custom_field")
    if seller_sku:
        sku_map[str(seller_sku).strip().upper()] = item_id

    for variation in item.get("variations", []):
        var_sku = variation.get("seller_custom_field")
        if var_sku:
            sku_map[str(var_sku).strip().upper()] = item_id
        for attr in variation.get("attribute_combinations", []):
            if attr.get("id") in ("SELLER_SKU", "SKU"):
                val = attr.get("value_name", "")
                if val:
                    sku_map[str(val).strip().upper()] = item_id
