from sqlalchemy import text


def list_emails(engine):
    with engine.connect() as conn:
        result = conn.execute(text("SELECT email FROM users ORDER BY id"))
        return [row.email for row in result]
