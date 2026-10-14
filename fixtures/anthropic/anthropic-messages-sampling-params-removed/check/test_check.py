import json
import sys

import anthropic

# The HTTP library the SDK just imported: httpx before 1.0, httpx2 from 1.0.
httpx = sys.modules.get("httpx2") or sys.modules["httpx"]

REPLY = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-4-6",
         "content": [{"type": "text", "text": "Positive"}], "stop_reason": "end_turn",
         "stop_sequence": None, "usage": {"input_tokens": 9, "output_tokens": 1}}


def make_client(sent):
    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=REPLY)

    return anthropic.Anthropic(api_key="test", base_url="http://mock.test", max_retries=0,
                               http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_classify_sentiment():
    import target

    sent = []
    assert target.classify_sentiment(make_client(sent), "Arrived early, works great.") == "positive"
    assert len(sent) == 1
    # The review must reach the model; wrapping it in a prompt is fine.
    assert "Arrived early, works great." in json.dumps(sent[0]["messages"])
