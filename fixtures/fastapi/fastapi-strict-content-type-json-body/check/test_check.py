from fastapi.testclient import TestClient

import target


def test_post_item_creates_item():
    client = TestClient(target.app)
    response = target.post_item(client, {"name": "widget", "quantity": 3})
    assert response.status_code == 200, response.text
    assert response.json() == {"name": "widget", "quantity": 3}
