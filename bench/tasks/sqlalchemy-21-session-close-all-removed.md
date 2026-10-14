<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Please write `target.py` with one helper for our SQLAlchemy ORM setup:
`close_open_sessions()`, which closes every ORM Session that is still open anywhere in the
process (all of them, not just one we hold a reference to), so that any transactions they
started are released. We call it from application shutdown and from test teardown. It takes
no arguments and returns nothing.
