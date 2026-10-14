import io
import json
from urllib.parse import urlsplit

import requests
import urllib3
from azure.ai.translation.document import DocumentTranslationClient
from azure.core.credentials import AzureKeyCredential
from requests.adapters import HTTPAdapter

ENDPOINT = "https://contoso.cognitiveservices.azure.com"
OP = "0b5e4a1c-6d1f-4c8e-9a51-2f6a1f0d7c11"
SENT = []


def fake_send(self, request, **kwargs):
    """Plays the Document Translation batch API; no network."""
    path = urlsplit(request.url).path
    resp = requests.Response()
    resp.url, resp.request = request.url, request
    resp.headers["Content-Type"] = "application/json"
    if request.method == "POST" and path.endswith("/batches"):
        SENT.append(json.loads(request.body))
        resp.status_code, resp._content = 202, b""
        resp.headers["Operation-Location"] = f"{ENDPOINT}/translator/document/batches/{OP}"
    elif request.method == "GET" and path.endswith(f"/batches/{OP}"):
        status = {"id": OP, "createdDateTimeUtc": "2026-10-01T00:00:00Z", "lastActionDateTimeUtc": "2026-10-01T00:00:00Z",
                  "status": "NotStarted", "summary": {"total": 0, "failed": 0, "success": 0, "inProgress": 0,
                                                      "notYetStarted": 0, "cancelled": 0, "totalCharacterCharged": 0}}
        resp.status_code, resp._content = 200, json.dumps(status).encode()
    else:
        resp.status_code, resp._content = 404, b'{"error": {"code": "NotFound", "message": "no route"}}'
    resp.raw = urllib3.HTTPResponse(body=io.BytesIO(resp._content), preload_content=False)
    return resp


def test_start_batch_translation(monkeypatch):
    monkeypatch.setattr(HTTPAdapter, "send", fake_send)
    import target

    client = DocumentTranslationClient(ENDPOINT, AzureKeyCredential("key"))
    targets = {"de": "https://acct.blob.core.windows.net/de?sas", "fr": "https://acct.blob.core.windows.net/fr?sas"}
    assert target.start_batch_translation(client, "https://acct.blob.core.windows.net/src?sas", targets) == OP
    (job,) = SENT[-1]["inputs"]
    assert job["source"]["sourceUrl"] == "https://acct.blob.core.windows.net/src?sas"
    assert {t["language"]: t["targetUrl"] for t in job["targets"]} == targets
