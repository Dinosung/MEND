<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
PATCH endpoint for user profiles: clients send only the fields they want to change. Please
write `target.py` with a pydantic model `UserProfileUpdate` with optional `display_name`,
`bio` and `avatar_url` string fields, and `parse_update(payload: dict) -> dict` that
validates the payload and returns only the fields that were actually provided, e.g. `{"bio":
"hello"}` -> `{"bio": "hello"}` and `{}` -> `{}`.
