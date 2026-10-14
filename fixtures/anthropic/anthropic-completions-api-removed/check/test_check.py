import json
import sys

import anthropic

# The HTTP library the SDK just imported: httpx before 1.0, httpx2 from 1.0.
httpx = sys.modules.get("httpx2") or sys.modules["httpx"]

TITLE = "Q3 roadmap review"
REPLIES = {
    "/v1/messages": {"id": "msg_1", "type": "message", "role": "assistant",
                     "model": "claude-sonnet-4-6", "content": [{"type": "text", "text": TITLE}],
                     "stop_reason": "end_turn", "stop_sequence": None,
                     "usage": {"input_tokens": 20, "output_tokens": 4}},
    "/v1/complete": {"id": "compl_1", "type": "completion", "model": "claude-sonnet-4-6",
                     "completion": " " + TITLE, "stop_reason": "stop_sequence"},
}


def make_client(sent):
    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=REPLIES[request.url.path])

    return anthropic.Anthropic(api_key="test", base_url="http://mock.test", max_retries=0,
                               http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_suggest_title():
    import target

    sent = []
    assert target.suggest_title(make_client(sent), "- ship search\n- hire 2 SREs") == TITLE
    assert len(sent) == 1
    assert "ship search" in json.dumps(sent[0])
