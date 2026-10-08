"""Test helpers: fake clock, in-process WSGI client and fault-injecting transport. Synthetic data only."""
import io
import json
from pathlib import Path
import tempfile

from arkos_relay.agent import ApiError, TransportError
from arkos_relay.api import App
from arkos_relay.store import Store


class Clock:
    def __init__(self, now=1_800_000_000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def wsgi(app, method, path, body=None, token=None, headers=None, raw=None, remote="10.0.0.1"):
    query = ""
    if "?" in path:
        path, query = path.split("?", 1)
    data = raw if raw is not None else (b"" if body is None else json.dumps(body).encode())
    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query, "CONTENT_LENGTH": str(len(data)),
               "CONTENT_TYPE": "application/json", "wsgi.input": io.BytesIO(data), "REMOTE_ADDR": remote}
    if token:
        environ["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    for key, value in (headers or {}).items():
        environ["HTTP_" + key.upper().replace("-", "_")] = value
    captured = {}
    chunks = app(environ, lambda status, hdrs: captured.update(status=int(status.split()[0]), headers=dict(hdrs)))
    payload = b"".join(chunks)
    if captured["headers"]["Content-Type"].startswith("application/json"):
        return captured["status"], json.loads(payload)
    return captured["status"], payload.decode()


class InProcessTransport:
    """Agent transport over the WSGI app, with optional failures per call."""

    def __init__(self, app, token):
        self.app, self.token = app, token
        self.offline = False
        self.drop_response = set()  # paths whose request reaches the server but the response is lost
        self.calls = []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path))
        if self.offline:
            raise TransportError("offline")
        status, payload = wsgi(self.app, method, path, body, self.token)
        if any(path.endswith(suffix) for suffix in self.drop_response):
            self.drop_response = {s for s in self.drop_response if not path.endswith(s)}
            raise TransportError("response lost")
        if status >= 400:
            raise ApiError(status, payload["error"]["code"], payload["error"]["message"])
        return payload


class RelayFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.clock = Clock()
        self.store = Store(self.dir / "relay.sqlite3", clock=self.clock)
        self.app = App(self.store)
        self.alice = self.store.create_user("Alice Sintética")
        self.alice_token = self.store.issue_user_token(self.alice)
        self.bob = self.store.create_user("Bob Sintético")
        self.bob_token = self.store.issue_user_token(self.bob)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def restart_server(self):
        self.store.close()
        self.store = Store(self.dir / "relay.sqlite3", clock=self.clock)
        self.app = App(self.store)

    def call(self, method, path, body=None, token=None):
        return wsgi(self.app, method, path, body, token)

    def pair(self, user_token, name="PC sintética"):
        status, code = self.call("POST", "/v1/devices/pairing-codes", {"device_name": name}, user_token)
        assert status == 201, code
        status, device = self.call("POST", "/v1/pair", {"code": code["code"]})
        assert status == 201, device
        return device

    def create(self, token, text="Preparar propuesta sintética", request_id="req-00000001", action="note.create", params=None, **extra):
        body = {"client_request_id": request_id, "action": action, "params": params or {"text": text}, **extra}
        return self.call("POST", "/v1/tasks", body, token)

    def approve(self, token, task, ttl=3600):
        return self.call("POST", f"/v1/tasks/{task['id']}/approve", {"payload_sha256": task["payload_sha256"], "ttl_seconds": ttl}, token)
