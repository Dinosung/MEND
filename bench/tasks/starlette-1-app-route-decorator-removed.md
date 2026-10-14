<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
A minimal Starlette service, please (no FastAPI). Write `target.py` with a Starlette `app`
with two JSON endpoints: `GET /health` returning `{"status": "ok"}` and `GET
/users/{user_id}` where `user_id` is an int path parameter, returning `{"id": user_id}`.
