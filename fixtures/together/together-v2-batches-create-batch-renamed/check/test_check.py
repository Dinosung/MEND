import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from together import Together

JOB = {"id": "batch-42", "user_id": "u1", "input_file_id": "file-abc", "file_size_bytes": 10,
       "status": "VALIDATING", "job_deadline": "2026-10-15T00:00:00Z",
       "created_at": "2026-10-14T00:00:00Z", "endpoint": "/v1/chat/completions"}
SENT = []


class FakeAPI(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        SENT.append((self.path, json.loads(body or b"{}")))
        data = json.dumps({"job": JOB}).encode() if self.path == "/v1/batches" else b"{}"
        self.send_response(200 if self.path == "/v1/batches" else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def test_submit_batch(monkeypatch):
    import target

    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    server = HTTPServer(("127.0.0.1", 0), FakeAPI)  # loopback only: the SDK's HTTP stack differs by version
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = Together(api_key="test", base_url=f"http://127.0.0.1:{server.server_port}/v1",
                          max_retries=0)
        assert target.submit_batch(client, "file-abc") == "batch-42"
    finally:
        server.shutdown()
    assert [p for p, _ in SENT] == ["/v1/batches"]
    assert SENT[0][1]["input_file_id"] == "file-abc"
    assert SENT[0][1]["endpoint"] == "/v1/chat/completions"
