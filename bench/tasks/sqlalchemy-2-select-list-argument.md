<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Please write `target.py` using SQLAlchemy Core (no ORM): a module-level `metadata` and a
`users` Table with columns `id` (integer primary key), `email` (string) and `active`
(boolean), plus `active_emails(conn)` that builds a SELECT of the email column for active
users ordered by id, executes it on the given connection and returns a list of email
strings.
