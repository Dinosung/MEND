<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Please write `target.py` with `find_email(engine, user_id)` using SQLAlchemy: it looks up a
user's email in the `users` table (`id`, `email`) with a raw SQL query that passes `user_id`
as a bound parameter (no string formatting), and returns the email or `None` if there is no
such user.
