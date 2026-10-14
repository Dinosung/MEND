import polars as pl


def test_sales_to_long():
    import target

    wide = pl.DataFrame({"store": ["north", "south"], "jan": [10, 20], "feb": [11, 21]})
    out = target.sales_to_long(wide)
    assert out.columns == ["store", "month", "sales"]
    assert sorted(out.rows()) == [
        ("north", "feb", 11), ("north", "jan", 10), ("south", "feb", 21), ("south", "jan", 20),
    ]
