import asyncio
import json
import sys

import anthropic

# The HTTP library the SDK just imported: httpx before 1.0, httpx2 from 1.0.
httpx = sys.modules.get("httpx2") or sys.modules["httpx"]

QUESTION = "What is the capital of Australia?"
REPLY = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-4-6",
         "content": [{"type": "text", "text": "Canberra."}], "stop_reason": "end_turn",
         "stop_sequence": None, "usage": {"input_tokens": 9, "output_tokens": 3}}


def test_ask():
    import target

    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=REPLY, headers={"anthropic-ratelimit-requests-remaining": "41"})

    async def run():
        client = anthropic.AsyncAnthropic(
            api_key="test", base_url="http://mock.test", max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        return await target.ask(client, QUESTION)

    text, remaining = asyncio.run(run())
    assert text.strip() == "Canberra."
    assert remaining == 41
    assert len(sent) == 1
    assert QUESTION in json.dumps(sent[0]["messages"])
