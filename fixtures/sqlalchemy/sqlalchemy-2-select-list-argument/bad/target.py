from sqlalchemy import Boolean, Column, Integer, MetaData, String, Table, select

metadata = MetaData()
users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String),
    Column("active", Boolean),
)


def active_emails(conn):
    stmt = select([users.c.email]).where(users.c.active == True).order_by(users.c.id)  # noqa: E712
    return conn.execute(stmt).scalars().all()
