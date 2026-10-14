from starlette.testclient import TestClient

import target


def test_routes_respond():
    client = TestClient(target.app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/users/42").json() == {"id": 42}
