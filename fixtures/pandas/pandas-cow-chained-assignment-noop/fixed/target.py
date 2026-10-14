import pandas as pd


def clip_negative_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Data-cleaning step: negative prices are entry errors, set them to 0."""
    df = df.copy()
    df.loc[df["price"] < 0, "price"] = 0
    return df
