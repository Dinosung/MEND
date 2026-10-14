import pydantic


def test_cross_field_validation():
    import target

    ok = target.change_password({"password": "s3cret", "password_confirm": "s3cret"})
    assert ok.password == "s3cret"

    try:
        target.change_password({"password": "s3cret", "password_confirm": "other"})
    except pydantic.ValidationError as exc:
        assert "passwords do not match" in str(exc)
    else:
        raise AssertionError("mismatched passwords were accepted")
