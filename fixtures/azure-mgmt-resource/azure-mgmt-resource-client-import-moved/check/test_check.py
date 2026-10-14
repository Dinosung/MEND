import io
import json
import time

import requests
import urllib3
from azure.core.credentials import AccessToken

SUB = "00000000-0000-0000-0000-000000000001"
GROUPS = [{"id": f"/subscriptions/{SUB}/resourceGroups/rg-web", "name": "rg-web", "location": "westeurope",
           "properties": {"provisioningState": "Succeeded"}},
          {"id": f"/subscriptions/{SUB}/resourceGroups/rg-data", "name": "rg-data", "location": "eastus2",
           "properties": {"provisioningState": "Succeeded"}}]


class FakeCredential:
    def get_token(self, *scopes, **kwargs):
        return AccessToken("fake-token", int(time.time()) + 3600)


def fake_arm(self, method, url, *args, **kwargs):
    """Stands in for Azure Resource Manager at the HTTP layer; no network."""
    resp = requests.Response()
    resp.url, resp.request = url, requests.Request(method, url).prepare()
    resp.headers["Content-Type"] = "application/json"
    if method.upper() == "GET" and f"/subscriptions/{SUB}/resourcegroups" in url.lower():
        resp.status_code, resp._content = 200, json.dumps({"value": GROUPS}).encode()
    else:
        resp.status_code, resp._content = 404, b'{"error": {"code": "NotFound", "message": "no route"}}'
    resp.raw = urllib3.HTTPResponse(body=io.BytesIO(resp._content), preload_content=False)
    return resp


def test_resource_group_locations(monkeypatch):
    monkeypatch.setattr(requests.Session, "request", fake_arm)
    import target

    result = target.resource_group_locations(FakeCredential(), SUB)
    assert dict(result) == {"rg-web": "westeurope", "rg-data": "eastus2"}
