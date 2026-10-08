"""Synthetic OpenAI-compatible server for bridge tests. Records request bodies; scripted replies. Not a model."""
import json, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class FakeLLM:
    def __init__(self, script):
        self.script = list(script)   # each item: {"content": str} or {"tool_call": (name, args)} or {"sleep": s, ...}
        self.requests = []
        fake = self
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def handle(self):
                try:
                    super().handle()
                except (BrokenPipeError, ConnectionResetError):
                    pass  # client cancelled or was killed mid-response
            def do_GET(self):
                body = json.dumps({"object": "list", "data": [{"id": "synthetic", "object": "model"}]}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                fake.requests.append({"path": self.path, "body": req})
                if not self.path.endswith("/chat/completions"):
                    self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers(); return
                step = fake.script.pop(0) if fake.script else {"content": "fin"}
                if step.get("sleep"): time.sleep(step["sleep"])
                msg = {"role": "assistant", "content": step.get("content")}
                finish = "stop"
                if "tool_call" in step:
                    name, args = step["tool_call"]
                    msg["tool_calls"] = [{"id": "call_1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]
                    finish = "tool_calls"
                if req.get("stream"):
                    self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
                    delta = {"role": "assistant"}
                    if msg.get("content"): delta["content"] = msg["content"]
                    if msg.get("tool_calls"):
                        tc = msg["tool_calls"][0]
                        delta["tool_calls"] = [{"index": 0, "id": tc["id"], "type": "function", "function": tc["function"]}]
                    for chunk in ({"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                                  {"choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                                   "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}):
                        chunk.update(id="cmpl-1", object="chat.completion.chunk", created=0, model="synthetic")
                        self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n"); self.wfile.flush()
                    self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
                    return
                body = json.dumps({"id": "cmpl-1", "object": "chat.completion", "created": 0, "model": "synthetic",
                                   "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
                                   "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
    def close(self):
        self.server.shutdown(); self.server.server_close()
