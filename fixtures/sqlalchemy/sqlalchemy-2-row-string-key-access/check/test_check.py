from sqlalchemy import create_engine, text

import target


def test_get_user_returns_dict():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, active BOOLEAN)"))
        conn.execute(text("INSERT INTO users (id, email, active) VALUES (7, 'a@x.io', 1)"))
    with engine.connect() as conn:
        assert target.get_user(conn, 7) == {"id": 7, "email": "a@x.io", "active": True}
