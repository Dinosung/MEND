import io
import json
import time

import requests
import urllib3
from azure.core.credentials import AccessToken

SUBS = [{"id": "/subscriptions/1111", "subscriptionId": "1111", "displayName": "Prod", "state": "Enabled"},
        {"id": "/subscriptions/2222", "subscriptionId": "2222", "displayName": "Old", "state": "Disabled"},
        {"id": "/subscriptions/3333", "subscriptionId": "3333", "displayName": "Dev", "state": "Enabled"}]


class FakeCredential:
    def get_token(self, *scopes, **kwargs):
        return AccessToken("fake-token", int(time.time()) + 3600)


def fake_arm(self, method, url, *args, **kwargs):
    """Stands in for Azure Resource Manager at the HTTP layer; no network."""
    resp = requests.Response()
    resp.url, resp.request = url, requests.Request(method, url).prepare()
    resp.headers["Content-Type"] = "application/json"
    if method.upper() == "GET" and url.split("?")[0].rstrip("/").endswith("management.azure.com/subscriptions"):
        resp.status_code, resp._content = 200, json.dumps({"value": SUBS}).encode()
    else:
        resp.status_code, resp._content = 404, b'{"error": {"code": "NotFound", "message": "no route"}}'
    resp.raw = urllib3.HTTPResponse(body=io.BytesIO(resp._content), preload_content=False)
    return resp


def test_enabled_subscriptions(monkeypatch):
    monkeypatch.setattr(requests.Session, "request", fake_arm)
    import target

    assert dict(target.enabled_subscriptions(FakeCredential())) == {"1111": "Prod", "3333": "Dev"}
