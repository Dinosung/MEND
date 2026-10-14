<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Please write `target.py` with `get_user(conn, user_id)` using SQLAlchemy: given an open
connection, fetch the user with that id from the `users` table (`id`, `email`, `active`)
with a raw SQL query using a bound parameter, and return a dict `{"id": ..., "email": ...,
"active": ...}` built by reading the row's columns by name, with `active` as a Python bool.
