import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from together import Together

ROWS = [{"custom_id": "q1", "response": {"body": {"choices": [{"message": {"content": "4"}}]}}},
        {"custom_id": "q2", "response": {"body": {"choices": [{"message": {"content": "9"}}]}}}]
DATA = "".join(json.dumps(r) + "\n" for r in ROWS).encode()
SEEN = []


class FakeAPI(BaseHTTPRequestHandler):
    def do_GET(self):
        SEEN.append(self.path)
        ok = self.path == "/v1/files/file-out/content"
        self.send_response(200 if ok else 404)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(DATA) if ok else 0))
        self.end_headers()
        if ok:
            self.wfile.write(DATA)

    def log_message(self, *args):
        pass


def test_save_batch_results(monkeypatch, tmp_path):
    import target

    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    server = HTTPServer(("127.0.0.1", 0), FakeAPI)  # loopback only: the SDK's HTTP stack differs by version
    threading.Thread(target=server.serve_forever, daemon=True).start()
    out = tmp_path / "results.jsonl"
    try:
        client = Together(api_key="test", base_url=f"http://127.0.0.1:{server.server_port}/v1",
                          max_retries=0)
        records = target.save_batch_results(client, "file-out", str(out))
    finally:
        server.shutdown()
    assert out.read_bytes() == DATA
    assert [r["custom_id"] for r in records] == ["q1", "q2"]
    assert "/v1/files/file-out/content" in SEEN
