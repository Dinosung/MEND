class FakeOrmUser:
    """Stands in for an ORM row: data lives on attributes, not in a dict."""

    def __init__(self):
        self.id = 7
        self.email = "ada@example.com"
        self.is_active = True


def test_orm_object_is_converted():
    import target

    assert target.serialize_user(FakeOrmUser()) == {
        "id": 7,
        "email": "ada@example.com",
        "is_active": True,
    }
