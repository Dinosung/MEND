from sqlalchemy import create_engine, text

import target


def make_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)"))
        conn.execute(text("INSERT INTO users (email) VALUES ('a@x.io'), ('b@x.io')"))
    return engine


def test_lists_emails_in_order():
    assert target.list_emails(make_engine()) == ["a@x.io", "b@x.io"]
