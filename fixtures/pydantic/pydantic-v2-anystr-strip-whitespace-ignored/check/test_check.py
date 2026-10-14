def test_strings_are_stripped_and_lowercased():
    import target

    form = target.parse_signup({"username": "  Ada  ", "email": " Ada@Example.COM\n"})
    assert form.username == "ada"
    assert form.email == "ada@example.com"
