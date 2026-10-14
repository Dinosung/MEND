import json
import sys

import anthropic

# The HTTP library the SDK just imported: httpx before 1.0, httpx2 from 1.0.
httpx = sys.modules.get("httpx2") or sys.modules["httpx"]

QUESTION = "Name a prime number between 10 and 15."
REPLY = {"id": "msg_7", "type": "message", "role": "assistant", "model": "claude-sonnet-4-6",
         "content": [{"type": "text", "text": "11"}], "stop_reason": "end_turn",
         "stop_sequence": None, "usage": {"input_tokens": 12, "output_tokens": 1}}


def test_ask_and_archive(tmp_path):
    import target

    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=REPLY)

    client = anthropic.Anthropic(api_key="test", base_url="http://mock.test", max_retries=0,
                                 http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    out = tmp_path / "archive.json"
    assert target.ask_and_archive(client, QUESTION, str(out)).strip() == "11"
    assert json.loads(out.read_text(encoding="utf-8")) == REPLY
    assert len(sent) == 1
    assert QUESTION in json.dumps(sent[0]["messages"])
