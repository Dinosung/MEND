import pandas as pd


def monthly_revenue(sales: pd.DataFrame) -> pd.Series:
    """Total sales amount per calendar month (labelled by month end)."""
    return sales.resample("M", on="date")["amount"].sum()


def hourly_counts(events: pd.DataFrame) -> pd.Series:
    """Number of events per hour."""
    return events.resample("H", on="ts").size()
