<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
I'm collecting orders from an API one at a time. Please write `target.py` with
`orders_to_frame(orders)` that takes a list of order dicts like `{"sku": "A1", "qty": 3}`
and builds a pandas DataFrame with columns `sku` and `qty`, one row per order in the
original order, with a default 0..n-1 index.
