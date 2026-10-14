import pandas as pd
from pandas.api.types import is_string_dtype


def normalize_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace and lowercase every text column before deduplication."""
    df = df.copy()
    for col in df.columns:
        if is_string_dtype(df[col]):
            df[col] = df[col].str.strip().str.lower()
    return df
