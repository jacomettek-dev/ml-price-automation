import pandas as pd

_SKU_ALIASES = {"sku", "código", "codigo", "cod", "ref", "referencia", "referência", "product_id"}
_PRICE_ALIASES = {"preço", "preco", "price", "valor", "venda", "preco_sugerido", "preço_sugerido", "preco sugerido", "preço sugerido"}


def _find_column(df: pd.DataFrame, aliases: set[str]) -> str | None:
    for col in df.columns:
        if col.strip().lower() in aliases:
            return col
    return None


def read_price_sheet(path: str) -> pd.DataFrame:
    """
    Lê um arquivo .xlsx e retorna DataFrame com colunas normalizadas:
      - sku (str, maiúsculo)
      - preco_sugerido (float)
    """
    df = pd.read_excel(path, dtype=str)
    df.columns = df.columns.str.strip()

    sku_col = _find_column(df, _SKU_ALIASES)
    price_col = _find_column(df, _PRICE_ALIASES)

    if not sku_col:
        raise ValueError(
            f"Coluna de SKU não encontrada. Colunas disponíveis: {list(df.columns)}\n"
            "Renomeie a coluna para 'SKU' ou 'Código'."
        )
    if not price_col:
        raise ValueError(
            f"Coluna de preço não encontrada. Colunas disponíveis: {list(df.columns)}\n"
            "Renomeie a coluna para 'Preço', 'Preço Sugerido' ou 'Valor'."
        )

    result = pd.DataFrame()
    result["sku"] = df[sku_col].str.strip().str.upper()
    result["preco_sugerido"] = (
        df[price_col]
        .str.replace("R$", "", regex=False)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.strip()
        .astype(float)
    )
    result = result.dropna(subset=["sku", "preco_sugerido"])
    result = result[result["sku"] != ""]
    return result.reset_index(drop=True)
