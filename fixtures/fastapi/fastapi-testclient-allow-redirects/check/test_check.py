from fastapi.testclient import TestClient

import target


def test_old_docs_redirects_to_docs():
    client = TestClient(target.app)
    assert target.redirect_location(client, "/old-docs") == "/docs"
