def list_emails(engine):
    with engine.connect() as conn:
        result = conn.execute("SELECT email FROM users ORDER BY id")
        return [row.email for row in result]
