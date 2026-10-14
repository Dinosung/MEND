from sqlalchemy import text


def count_active_users(engine):
    result = engine.execute(text("SELECT count(*) FROM users WHERE active = 1"))
    return result.scalar()
