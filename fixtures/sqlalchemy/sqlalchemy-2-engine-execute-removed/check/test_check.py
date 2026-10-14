from sqlalchemy import create_engine, text

import target


def make_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, active BOOLEAN)"))
        conn.execute(
            text("INSERT INTO users (email, active) VALUES ('a@x.io', 1), ('b@x.io', 0), ('c@x.io', 1)")
        )
    return engine


def test_counts_active_users():
    assert target.count_active_users(make_engine()) == 2
