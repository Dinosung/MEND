<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Our FastAPI service needs to open a (fake) database pool when the app starts and close it on
shutdown. Please write `target.py` with a module-level dict `resources`, functions
`open_pool()` (sets `resources["db"] = "connected"`) and `close_pool()` (removes that key),
and a FastAPI `app` that calls them on startup and shutdown respectively. Add a `GET
/health` route returning `{"db": resources.get("db")}`.
