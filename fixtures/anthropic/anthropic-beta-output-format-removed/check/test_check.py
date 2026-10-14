import json
import sys

import anthropic

# The HTTP library the SDK just imported: httpx before 1.0, httpx2 from 1.0.
httpx = sys.modules.get("httpx2") or sys.modules["httpx"]

DATA = {"vendor": "Acme Tools", "total": 412.5}
REPLY = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-4-6",
         "content": [{"type": "text", "text": json.dumps(DATA)}], "stop_reason": "end_turn",
         "stop_sequence": None, "usage": {"input_tokens": 30, "output_tokens": 12}}


def make_client(sent):
    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=REPLY)

    return anthropic.Anthropic(api_key="test", base_url="http://mock.test", max_retries=0,
                               http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_extract_invoice_requests_json_schema_output():
    import target

    sent = []
    assert target.extract_invoice(make_client(sent), "ACME TOOLS ... TOTAL DUE $412.50") == DATA
    assert len(sent) == 1
    assert sent[0]["output_config"]["format"]["type"] == "json_schema"
