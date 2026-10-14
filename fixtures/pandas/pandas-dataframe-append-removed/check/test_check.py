def test_orders_collected_in_order():
    import target

    df = target.orders_to_frame([{"sku": "A1", "qty": 3}, {"sku": "B2", "qty": 5}])
    assert list(df.columns) == ["sku", "qty"]
    assert df["sku"].tolist() == ["A1", "B2"]
    assert df["qty"].tolist() == [3, 5]
    assert df.index.tolist() == [0, 1]
