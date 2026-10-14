from sqlalchemy import column, func, select


def count_rows(conn, stmt):
    """Total number of rows `stmt` returns (for pagination)."""
    return conn.execute(select(func.count()).select_from(stmt)).scalar_one()


def rows_where_total_at_least(conn, stmt, minimum):
    """Rows of `stmt` whose labelled `total` column is >= minimum."""
    return conn.execute(stmt.select().where(column("total") >= minimum)).all()
