import pandas as pd


def test_negative_prices_are_zeroed():
    import target

    df = pd.DataFrame({"sku": ["a", "b", "c"], "price": [9.5, -1.0, -3.0]})
    out = target.clip_negative_prices(df)
    assert out["price"].tolist() == [9.5, 0.0, 0.0]
