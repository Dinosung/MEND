<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
One of our endpoints receives a bare JSON array as its body, e.g. `[{"name": "a"}, {"name":
"b"}]`. Please write `target.py` with a pydantic `Tag` model (`name: str`) and a pydantic
model representing the whole array, and `parse_tags(raw_json: str) -> list[str]` that
validates the raw JSON string with that model and returns the tag names in order.
