from fastapi.testclient import TestClient

import target


def test_profile_page_renders():
    client = TestClient(target.app, raise_server_exceptions=False)
    response = client.get("/profile/ada")
    assert response.status_code == 200
    assert "<h1>Hello ada</h1>" in response.text
