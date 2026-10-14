import pandas as pd


def test_monthly_revenue():
    import target

    sales = pd.DataFrame({
        "date": pd.to_datetime(["2024-01-05", "2024-01-20", "2024-02-03"]),
        "amount": [100.0, 50.0, 70.0],
    })
    out = target.monthly_revenue(sales)
    assert out.tolist() == [150.0, 70.0]
    assert [d.strftime("%Y-%m-%d") for d in out.index] == ["2024-01-31", "2024-02-29"]


def test_hourly_counts():
    import target

    ts = pd.to_datetime(["2024-01-01 09:05", "2024-01-01 09:40", "2024-01-01 10:01"])
    out = target.hourly_counts(pd.DataFrame({"ts": ts}))
    assert out.tolist() == [2, 1]
