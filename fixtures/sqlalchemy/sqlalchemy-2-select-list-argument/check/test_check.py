from sqlalchemy import create_engine

import target


def test_returns_only_active_emails():
    engine = create_engine("sqlite://")
    target.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            target.users.insert(),
            [
                {"email": "a@x.io", "active": True},
                {"email": "b@x.io", "active": False},
                {"email": "c@x.io", "active": True},
            ],
        )
    with engine.connect() as conn:
        assert target.active_emails(conn) == ["a@x.io", "c@x.io"]
