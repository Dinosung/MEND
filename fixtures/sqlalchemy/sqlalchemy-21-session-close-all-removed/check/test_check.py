from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import target


def test_closes_all_open_sessions():
    engine = create_engine("sqlite://")
    SessionLocal = sessionmaker(bind=engine)
    first, second = SessionLocal(), SessionLocal()
    first.execute(text("SELECT 1"))
    second.execute(text("SELECT 1"))
    assert first.in_transaction() and second.in_transaction()

    target.close_open_sessions()

    assert not first.in_transaction()
    assert not second.in_transaction()
