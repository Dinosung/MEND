<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Product catalog validation with pydantic. Please write `target.py` with a model `Product`
with `sku: str` and `name: str`, where the SKU must match the format three uppercase
letters, a dash, four digits (e.g. `ABC-1234`), enforced declaratively on the field with a
regular expression. Add `parse_product(data: dict) -> Product`; invalid SKUs must raise a
validation error.
