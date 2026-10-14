from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, func, select

import target

metadata = MetaData()
orders = Table("orders", metadata, Column("id", Integer, primary_key=True),
               Column("customer", String), Column("amount", Integer))


def setup():
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(orders.insert(), [{"customer": "ann", "amount": 5},
                                       {"customer": "ann", "amount": 7},
                                       {"customer": "bob", "amount": 3}])
    totals = (select(orders.c.customer, func.sum(orders.c.amount).label("total"))
              .group_by(orders.c.customer).order_by(orders.c.customer))
    return engine, totals


def test_count_rows():
    engine, totals = setup()
    with engine.connect() as conn:
        assert target.count_rows(conn, totals) == 2
        assert target.count_rows(conn, select(orders.c.id)) == 3


def test_rows_where_total_at_least():
    engine, totals = setup()
    with engine.connect() as conn:
        rows = target.rows_where_total_at_least(conn, totals, 4)
    assert [tuple(r) for r in rows] == [("ann", 12)]
