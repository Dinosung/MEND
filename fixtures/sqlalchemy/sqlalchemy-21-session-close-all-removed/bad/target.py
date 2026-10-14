from sqlalchemy.orm import Session


def close_open_sessions():
    """Close every Session still open in this process (shutdown / test teardown)."""
    Session.close_all()
