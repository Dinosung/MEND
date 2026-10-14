import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

REPLY = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-4-6",
         "content": [{"type": "text", "text": "pong"}], "stop_reason": "end_turn",
         "stop_sequence": None, "usage": {"input_tokens": 3, "output_tokens": 1}}
SEEN = []


class FakeProxy(BaseHTTPRequestHandler):
    """A loopback forward proxy that answers for the API itself."""

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        SEEN.append((self.path, self.headers.get("x-api-key")))
        data = json.dumps(REPLY).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def test_requests_go_through_proxy(monkeypatch):
    import target

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://api.mock.test")
    proxy = HTTPServer(("127.0.0.1", 0), FakeProxy)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    try:
        client = target.make_client("test-key", f"http://127.0.0.1:{proxy.server_port}")
        message = client.messages.create(model="claude-sonnet-4-6", max_tokens=8,
                                         messages=[{"role": "user", "content": "ping"}])
    finally:
        proxy.shutdown()
    assert message.content[0].text == "pong"
    assert SEEN == [("http://api.mock.test/v1/messages", "test-key")]
