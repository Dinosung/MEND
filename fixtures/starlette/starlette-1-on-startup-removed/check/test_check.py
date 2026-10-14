from starlette.testclient import TestClient

import target


def test_startup_hook_warms_cache():
    with TestClient(target.app) as client:
        assert client.get("/").json() == {"greeting": "hello"}
