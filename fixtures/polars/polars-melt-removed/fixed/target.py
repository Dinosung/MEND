import polars as pl


def sales_to_long(df: pl.DataFrame) -> pl.DataFrame:
    """Wide table (store + one column per month) -> rows of (store, month, sales)."""
    months = [c for c in df.columns if c != "store"]
    return df.unpivot(on=months, index="store", variable_name="month", value_name="sales")
