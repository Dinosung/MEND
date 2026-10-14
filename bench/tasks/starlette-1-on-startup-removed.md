<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Our Starlette app warms an in-memory cache when it starts. Please write `target.py` with a
module-level dict `cache`, an async `warm_cache()` that sets `cache["greeting"] = "hello"`,
and a Starlette `app` that runs `warm_cache()` at application startup and serves `GET /`
returning `{"greeting": cache.get("greeting")}` as JSON.
