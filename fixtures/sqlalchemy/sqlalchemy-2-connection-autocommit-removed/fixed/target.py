from sqlalchemy import text


def add_user(engine, email):
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (email) VALUES (:email)"), {"email": email})
