<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Please write `target.py` with a pandas cleaning function `fill_missing(df)` for our orders
DataFrame: a missing `discount` means no discount, so fill those with 0.0, and the
placeholder region `"N/A"` in the `region` column should become `"unknown"`. Return the
cleaned DataFrame.
