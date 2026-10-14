from sqlalchemy import text


def add_user(engine, email):
    with engine.connect() as conn:
        conn.execute(text("INSERT INTO users (email) VALUES (:email)"), {"email": email})
