import pandas as pd


def fill_missing(df: pd.DataFrame) -> pd.DataFrame:
    """Missing discounts mean no discount; placeholder regions become 'unknown'."""
    df = df.copy()
    df["discount"] = df["discount"].fillna(0.0)
    df["region"] = df["region"].replace("N/A", "unknown")
    return df
