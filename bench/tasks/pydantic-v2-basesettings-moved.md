<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Our service reads its configuration from environment variables and I want that typed and
validated with pydantic instead of hand-rolled `os.environ` lookups. Please write
`target.py` with an `AppSettings` class that has `database_url` (string, default
`"sqlite:///local.db"`) and `debug` (bool, default `False`), populated from the
`DATABASE_URL` and `DEBUG` environment variables, plus a `load_settings()` function that
returns an `AppSettings` instance built from the current environment.
