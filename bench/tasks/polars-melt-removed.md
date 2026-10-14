<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Our monthly sales export is a wide polars DataFrame: a `store` column plus one integer column
per month (`jan`, `feb`, ...). Please write `target.py` with
`sales_to_long(df: pl.DataFrame) -> pl.DataFrame` that reshapes it into long format with
exactly the columns `store`, `month` (the original column name) and `sales`, one row per
store and month.
