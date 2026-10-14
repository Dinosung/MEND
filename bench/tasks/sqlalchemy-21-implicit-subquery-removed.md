<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
Please write `target.py` with two SQLAlchemy Core helpers that work on top of an existing
SELECT statement built elsewhere (for example a grouped query with a column labelled
`total`): `count_rows(conn, stmt)` returns, as an int, how many rows `stmt` would return
(we need it for pagination, so count in SQL rather than fetching the rows), and
`rows_where_total_at_least(conn, stmt, minimum)` runs a query over the rows of `stmt` that
keeps only those whose `total` column is >= `minimum` and returns the result rows as a list.
Both execute on the given connection.
