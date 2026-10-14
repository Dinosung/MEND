import pydantic


def test_credentials_are_immutable():
    import target

    creds = target.load_credentials()
    try:
        creds.region = "eu-west-1"
    except pydantic.ValidationError:
        pass
    else:
        raise AssertionError(f"model was mutated: region={creds.region!r}")
    assert creds.region == "us-east-1"
