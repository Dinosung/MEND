import html as htmllib
import io
import json
from urllib.parse import parse_qs, urlsplit

import requests
import urllib3
from azure.ai.translation.text import TextTranslationClient
from azure.core.credentials import AzureKeyCredential
from requests.adapters import HTTPAdapter

SOURCE = "<p>Free <b>shipping</b> today</p>"


def fake_translate(text, lang, is_html):
    # Without the HTML text type the service treats tags as words and mangles them.
    return f"[{lang}] {text}" if is_html else f"[{lang}] {htmllib.escape(text)}"


def fake_send(self, request, **kwargs):
    """Plays the Translator /translate endpoint for the api-version the SDK sends; no network."""
    query = parse_qs(urlsplit(request.url).query)
    body = json.loads(request.body)
    if query["api-version"] == ["3.0"]:  # classic wire format
        is_html = query.get("textType") == ["html"]
        payload = [{"translations": [{"to": lang, "text": fake_translate(i["text"], lang, is_html)}
                                     for lang in query["to"]]} for i in body]
    else:  # 2026-06-06 wire format
        payload = {"value": [{"translations": [
            {"language": t["language"], "text": fake_translate(i["text"], t["language"], i.get("textType") == "html")}
            for t in i["targets"]]} for i in body["inputs"]]}
    resp = requests.Response()
    resp.status_code, resp.url, resp.request = 200, request.url, request
    resp.headers["Content-Type"] = "application/json"
    resp._content = json.dumps(payload).encode()
    resp.raw = urllib3.HTTPResponse(body=io.BytesIO(resp._content), preload_content=False)
    return resp


def test_translate_html(monkeypatch):
    monkeypatch.setattr(HTTPAdapter, "send", fake_send)
    import target

    client = TextTranslationClient(credential=AzureKeyCredential("key"), region="westeurope")
    result = target.translate_html(client, SOURCE, ["de", "fr"])
    assert dict(result) == {"de": f"[de] {SOURCE}", "fr": f"[fr] {SOURCE}"}
