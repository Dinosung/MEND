import pandas as pd


def clip_negative_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Data-cleaning step: negative prices are entry errors, set them to 0."""
    df = df.copy()
    df["price"][df["price"] < 0] = 0
    return df
