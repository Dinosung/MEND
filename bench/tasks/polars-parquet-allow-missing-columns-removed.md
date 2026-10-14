<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
We write one parquet file of events per month, and newer files have gained columns that
older ones lack. Please write `target.py` with `load_events(paths: list[str]) -> pl.DataFrame`
that reads all the given files with polars in one call and returns a single DataFrame with the
columns of the first file; columns that are missing from a file should come back as nulls for
its rows instead of raising an error.
