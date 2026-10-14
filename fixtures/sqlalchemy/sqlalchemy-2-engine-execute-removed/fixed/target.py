from sqlalchemy import text


def count_active_users(engine):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT count(*) FROM users WHERE active = 1"))
        return result.scalar()
