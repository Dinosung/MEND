import polars as pl


def load_events(paths: list[str]) -> pl.DataFrame:
    """Read several parquet files into one frame; columns a file lacks become null."""
    return pl.read_parquet(paths, missing_columns="insert")
