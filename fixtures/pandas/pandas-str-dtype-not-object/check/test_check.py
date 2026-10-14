import pandas as pd


def test_text_columns_are_normalized():
    import target

    df = pd.DataFrame({"email": ["  Ann@X.io", "ann@x.io "], "visits": [1, 2]})
    out = target.normalize_text_columns(df)
    assert out["email"].tolist() == ["ann@x.io", "ann@x.io"]
    assert out["visits"].tolist() == [1, 2]
    assert len(out.drop_duplicates(subset="email")) == 1
