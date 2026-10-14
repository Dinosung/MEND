from fastapi.testclient import TestClient

import target


def test_startup_and_shutdown_hooks_run():
    with TestClient(target.app) as client:
        assert client.get("/health").json() == {"db": "connected"}
    assert "db" not in target.resources
