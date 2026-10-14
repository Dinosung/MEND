<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Please write `target.py` with `add_user(engine, email)` using SQLAlchemy: it inserts a row
into the existing `users` table (columns `id INTEGER PRIMARY KEY`, `email TEXT`) using a raw
SQL INSERT with a bound parameter. The insert must be durably saved, so that other
connections see it afterwards.
