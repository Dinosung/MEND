import pandas as pd


def test_missing_values_are_filled():
    import target

    df = pd.DataFrame({"discount": [0.1, None, 0.25], "region": ["EU", "N/A", "US"]})
    out = target.fill_missing(df)
    assert out["discount"].tolist() == [0.1, 0.0, 0.25]
    assert out["region"].tolist() == ["EU", "unknown", "US"]
