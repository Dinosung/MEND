def test_parse_bare_json_array():
    import target

    assert target.parse_tags('[{"name": "a"}, {"name": "b"}]') == ["a", "b"]
