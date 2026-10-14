from sqlalchemy import create_engine, text

import target


def make_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)"))
        conn.execute(text("INSERT INTO users (id, email) VALUES (1, 'a@x.io'), (2, 'b@x.io')"))
    return engine


def test_finds_email_by_id():
    engine = make_engine()
    assert target.find_email(engine, 2) == "b@x.io"
    assert target.find_email(engine, 99) is None
