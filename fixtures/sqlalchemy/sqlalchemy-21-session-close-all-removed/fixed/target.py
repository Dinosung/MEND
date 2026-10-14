from sqlalchemy.orm import close_all_sessions


def close_open_sessions():
    """Close every Session still open in this process (shutdown / test teardown)."""
    close_all_sessions()
