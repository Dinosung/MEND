<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Data cleaning step for our product feed with pandas: negative prices are data-entry errors.
Please write `target.py` with `clip_negative_prices(df)` that takes a DataFrame with `sku`
and `price` columns and returns a DataFrame where every negative price is set to 0. Other
rows stay unchanged.
