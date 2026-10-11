"""HTTP(S) front for CloudGateway.dispatch(). Standard library only.

- Binds to loopback by default. A non-loopback bind requires TLS (cert + key) or an explicit
  statement that a TLS-terminating proxy sits in front (--behind-tls-proxy).
- POST needs Content-Length (<= MAX_BODY_BYTES); Transfer-Encoding is refused. Small unread
  bodies of rejected requests are drained (bounded) so clients can read the answer.
- Per-address rate limit before authentication.
- Access log: method, route template, status and duration only. Never headers, tokens,
  request ids or bodies.
"""
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import re
import ssl
import sys
import threading
import time

from .gateway import MAX_BODY_BYTES

RATE_WINDOW_S = 60
RATE_LIMIT = 60          # requests per address per window
DRAIN_LIMIT = 64 * 1024
DRAIN_SECONDS = 1.0
_ROUTE = re.compile(r"^/v1/conversations(/[^/]+)?(/cancel)?$")


def _route_template(path):
    match = _ROUTE.match(path.split("?", 1)[0])
    if not match:
        return "/<otro>"
    return "/v1/conversations" + ("/<id>" if match.group(1) else "") + ("/cancel" if match.group(2) else "")


def is_loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class _RateLimiter:
    def __init__(self, limit, window):
        self.limit, self.window = limit, window
        self.hits = {}
        self.lock = threading.Lock()

    def allow(self, address):
        now = time.monotonic()
        with self.lock:
            hits = self.hits.setdefault(address, deque())
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            if len(self.hits) > 10_000:  # forget idle addresses
                for key in [k for k, v in self.hits.items() if not v]:
                    del self.hits[key]
            return True


class _Handler(BaseHTTPRequestHandler):
    server_version = "ArkosCloudGateway/1"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)
        self.started = time.monotonic()
        self.body_consumed = False

    def log_message(self, format, *args):  # replaced by _access_log
        pass

    def _access_log(self, status):
        if self.server.access_log is not None:
            elapsed = int((time.monotonic() - self.started) * 1000)
            print(f"{self.command} {_route_template(self.path)} {status} {elapsed}ms",
                  file=self.server.access_log, flush=True)

    def _send(self, status, body):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)
        self._access_log(status)
        if status >= 400:
            self._drain()

    def _drain(self):
        if self.command != "POST" or self.body_consumed:
            return
        self.body_consumed = True
        self.close_connection = True
        length = self.headers.get("Content-Length", "").strip()
        if self.headers.get("Transfer-Encoding") or not length.isdigit() or int(length) > DRAIN_LIMIT:
            return
        remaining, deadline = int(length), time.monotonic() + DRAIN_SECONDS
        try:
            while remaining > 0 and time.monotonic() < deadline:
                self.connection.settimeout(max(0.01, deadline - time.monotonic()))
                chunk = self.rfile.read1(min(remaining, 16384))
                if not chunk:
                    return
                remaining -= len(chunk)
        except OSError:
            return

    def _handle(self):
        if not self.server.limiter.allow(self.client_address[0]):
            return self._send(429, {"error": {"code": "rate_limited"}})
        body = b""
        if self.command == "POST":
            length = self.headers.get("Content-Length", "").strip()
            if self.headers.get("Transfer-Encoding") or not length.isdigit():
                return self._send(411, {"error": {"code": "invalid_request"}})
            if int(length) > MAX_BODY_BYTES:
                return self._send(413, {"error": {"code": "invalid_request"}})
            body = self.rfile.read(int(length))
            self.body_consumed = True
            if len(body) != int(length):
                return self._send(400, {"error": {"code": "invalid_request"}})
        try:
            status, payload = self.server.gateway.dispatch(self.command, self.path.split("?", 1)[0],
                                                           dict(self.headers.items()), body)
        except Exception:  # never leak internals
            status, payload = 500, {"error": {"code": "internal"}}
        self._send(status, payload)

    def do_POST(self):
        self._handle()

    def do_GET(self):
        self._handle()

    def _not_allowed(self):
        self._send(405, {"error": {"code": "invalid_request"}})

    do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _not_allowed


class GatewayServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, gateway, host="127.0.0.1", port=0, tls_cert=None, tls_key=None,
                 behind_tls_proxy=False, access_log=sys.stderr, rate_limit=RATE_LIMIT):
        if bool(tls_cert) != bool(tls_key):
            raise ValueError("TLS requiere certificado y clave")
        if not is_loopback(host) and not tls_cert and not behind_tls_proxy:
            raise ValueError("Fuera de loopback se requiere TLS o --behind-tls-proxy explícito")
        super().__init__((host, port), _Handler)
        self.gateway, self.access_log = gateway, access_log
        self.limiter = _RateLimiter(rate_limit, RATE_WINDOW_S)
        self.scheme = "https" if tls_cert else "http"
        if tls_cert:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(tls_cert, tls_key)
            # Handshake in the request thread, not in accept(): a slow client cannot stall others.
            self.socket = context.wrap_socket(self.socket, server_side=True, do_handshake_on_connect=False)

    def handle_error(self, request, client_address):
        """Failed handshakes and dropped clients are normal; never print tracebacks or addresses."""
        if self.access_log is not None:
            print("connection error", file=self.access_log, flush=True)

    @property
    def url(self):
        host, port = self.server_address[:2]
        return f"{self.scheme}://{host}:{port}"
