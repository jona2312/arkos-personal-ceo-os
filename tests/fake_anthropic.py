"""Local stand-in for the Messages API (loopback HTTP). No network, no keys, no cost.

Each request takes the next scripted action (default "ok"):
  "ok" | ("ok", text, input_tokens, output_tokens) | ("status", code) | "drop" | "hold" | "refusal"
"hold" waits for .release (threading.Event) before answering "ok".
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

DEFAULT_TEXT = ("Te propongo una nota.\n```arkos-proposal\n"
                '{"type": "note", "title": "Compras", "text": "Comprar café"}\n```')


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        fake = self.server.fake
        with fake.lock:
            fake.requests.append(dict(path=self.path, headers={k.lower(): v for k, v in self.headers.items()},
                                      body=body))
            action = fake.script.pop(0) if fake.script else "ok"
        fake.arrived.set()
        if action == "hold":
            fake.release.wait(15)
            action = "ok"
        if action == "drop":
            self.close_connection = True
            self.connection.shutdown(2)
            return
        if isinstance(action, tuple) and action[0] == "status":
            return self._json(action[1], {"type": "error", "error": {"type": "synthetic_error", "message": "fake"}})
        text, tokens_in, tokens_out, stop = DEFAULT_TEXT, 150, 60, "end_turn"
        if isinstance(action, tuple) and action[0] == "ok":
            _, text, tokens_in, tokens_out = action
        if action == "refusal":
            text, stop = "", "refusal"
        content = [{"type": "thinking", "thinking": "", "signature": "fake-signature"}]
        if text:
            content.append({"type": "text", "text": text})
        self._json(200, {"id": "msg_fake", "type": "message", "role": "assistant", "model": body.get("model"),
                         "content": content, "stop_reason": stop, "stop_sequence": None,
                         "usage": {"input_tokens": tokens_in, "output_tokens": tokens_out}})

    def _json(self, status, value):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        try:
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # the gateway was killed on purpose mid-call


class FakeAnthropic:
    def __init__(self):
        self.requests, self.script = [], []
        self.lock = threading.Lock()
        self.release, self.arrived = threading.Event(), threading.Event()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.server.daemon_threads = True
        self.server.fake = self
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
