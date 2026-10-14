import pandas as pd


def fill_missing(df: pd.DataFrame) -> pd.DataFrame:
    """Missing discounts mean no discount; placeholder regions become 'unknown'."""
    df = df.copy()
    df["discount"].fillna(0.0, inplace=True)
    df["region"].replace("N/A", "unknown", inplace=True)
    return df
