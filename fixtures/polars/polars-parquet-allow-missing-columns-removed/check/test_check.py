import polars as pl


def test_load_events_fills_missing_columns(tmp_path):
    import target

    new = tmp_path / "2026-02.parquet"
    old = tmp_path / "2026-01.parquet"
    pl.DataFrame({"user": [3], "event": ["buy"], "country": ["NL"]}).write_parquet(new)
    pl.DataFrame({"user": [1, 2], "event": ["view", "view"]}).write_parquet(old)

    out = target.load_events([str(new), str(old)])
    assert out.columns == ["user", "event", "country"]
    assert out.sort("user").rows() == [(1, "view", None), (2, "view", None), (3, "buy", "NL")]
