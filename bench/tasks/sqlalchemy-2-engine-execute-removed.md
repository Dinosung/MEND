<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Quick metrics helper with SQLAlchemy. Please write `target.py` with
`count_active_users(engine)` that, given a SQLAlchemy engine, runs a raw SQL count over the
`users` table (`id`, `email`, `active` boolean column) and returns the number of active
users as an int.
