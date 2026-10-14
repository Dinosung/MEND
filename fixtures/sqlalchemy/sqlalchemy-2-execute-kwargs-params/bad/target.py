from sqlalchemy import text


def find_email(engine, user_id):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT email FROM users WHERE id = :id"), id=user_id)
        return result.scalar_one_or_none()
