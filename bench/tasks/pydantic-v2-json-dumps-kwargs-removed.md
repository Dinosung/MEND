<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Invoice export with pydantic. Please write `target.py` with a model `Invoice` (`number:
str`, `customer: str`, `issued: date`, `total_cents: int`) and `export_invoice(invoice,
path: str) -> None` that writes the invoice to `path` as human-readable JSON: indented by 2
spaces, UTF-8, with non-ASCII characters such as accented customer names written as-is
rather than escaped. Dates should be ISO strings.
