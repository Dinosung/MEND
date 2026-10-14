from sqlalchemy import create_engine, text

import target


def test_inserted_user_is_persisted(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)"))

    target.add_user(engine, "a@x.io")

    with engine.connect() as conn:
        emails = conn.execute(text("SELECT email FROM users")).scalars().all()
    assert emails == ["a@x.io"]
