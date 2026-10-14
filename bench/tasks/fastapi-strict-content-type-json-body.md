<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
I need a tiny FastAPI app for creating inventory items. Please write `target.py` with an
`app` exposing `POST /items` that accepts an item with `name` (str) and `quantity` (int) in
the request body, validated with a pydantic model, and echoes back `{"name": ...,
"quantity": ...}`. Also add a helper `post_item(client, payload: dict)` that sends a payload
dict to that endpoint using a TestClient-style `client` and returns the response; our sync
script and tests use it.
