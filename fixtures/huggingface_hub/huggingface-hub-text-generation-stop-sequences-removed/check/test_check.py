import json

from huggingface_hub import InferenceClient, set_client_factory
from huggingface_hub.utils import httpx  # httpx before huggingface_hub 2.0, httpx2 from 2.0

PROMPT = "def add(a, b):\n"
BODY = "    return a + b"


def test_complete_function():
    import target

    sent = []

    def handler(request):
        payload = json.loads(request.content)
        sent.append(payload)
        stop = (payload.get("parameters") or {}).get("stop") or []
        text = BODY if "\n\n" in stop else BODY + "\n\n\nprint(add(1, 2))\n"
        return httpx.Response(200, json=[{"generated_text": text}])

    set_client_factory(lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    client = InferenceClient(base_url="http://tgi.mock.test")

    assert target.complete_function(client, PROMPT).rstrip() == BODY
    assert len(sent) == 1
    assert sent[0]["inputs"] == PROMPT
