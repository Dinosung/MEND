import pandas as pd


def normalize_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace and lowercase every text column before deduplication."""
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].str.strip().str.lower()
    return df
