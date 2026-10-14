import pandas as pd


def latest_close(closes: pd.Series) -> float:
    """Most recent closing price from a date-indexed, ascending series."""
    return float(closes[-1])


def first_close(closes: pd.Series) -> float:
    return float(closes[0])
