import json

import httpx

try:  # where the SDK exports the client depends on its version
    from mistralai.client import Mistral
except ImportError:
    from mistralai import Mistral

TICKET = "My invoice for March was charged twice."
REPLY = {"id": "c1", "object": "chat.completion", "model": "mistral-small-latest", "created": 1,
         "choices": [{"index": 0, "finish_reason": "stop",
                      "message": {"role": "assistant", "content": " Customer was double-billed. "}}],
         "usage": {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13}}


def test_summarize():
    import target

    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=REPLY)

    client = Mistral(api_key="test", server_url="http://mock.test",
                     client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert target.summarize(client, TICKET) == "Customer was double-billed."
    assert len(sent) == 1
    assert TICKET in json.dumps(sent[0]["messages"])


def test_make_client():
    import target

    client = target.make_client("test-key")
    assert type(client).__name__ == "Mistral"
    assert hasattr(client.chat, "complete")
