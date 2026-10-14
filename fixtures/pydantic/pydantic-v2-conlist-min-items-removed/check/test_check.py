import pydantic


def test_list_length_bounds_enforced():
    import target

    ok = target.parse_invite({"team_id": 1, "emails": ["a@example.com"]})
    assert ok.emails == ["a@example.com"]
    for bad in ([], ["x@example.com"] * 51):
        try:
            target.parse_invite({"team_id": 1, "emails": bad})
        except pydantic.ValidationError:
            continue
        raise AssertionError(f"list of length {len(bad)} was accepted")
