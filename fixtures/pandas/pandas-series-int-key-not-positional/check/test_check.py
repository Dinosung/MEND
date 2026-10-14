import pandas as pd


def _closes():
    idx = pd.date_range("2024-03-01", periods=3, freq="D")
    return pd.Series([101.5, 99.0, 103.25], index=idx, name="close")


def test_latest_close():
    import target

    assert target.latest_close(_closes()) == 103.25


def test_first_close():
    import target

    assert target.first_close(_closes()) == 101.5
