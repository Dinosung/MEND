def test_partial_update_accepts_missing_optional_fields():
    import target

    assert target.parse_update({"bio": "hello"}) == {"bio": "hello"}
    assert target.parse_update({}) == {}
