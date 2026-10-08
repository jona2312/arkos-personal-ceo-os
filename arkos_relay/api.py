"""WSGI API for the relay. Stdlib only; run behind a TLS-terminating proxy."""
import json
import re
import threading
import time

from . import CONTRACT_VERSION
from .contract import ContractError
from .store import RelayError

MAX_BODY = 256 * 1024


class FailureThrottle:
    """In-memory limit on failed pairing attempts per client address."""

    def __init__(self, limit=10, window=600, clock=time.time):
        self.limit, self.window, self.clock = limit, window, clock
        self.failures = {}
        self.lock = threading.Lock()

    def blocked(self, key):
        with self.lock:
            recent = [t for t in self.failures.get(key, []) if t > self.clock() - self.window]
            self.failures[key] = recent
            return len(recent) >= self.limit

    def fail(self, key):
        with self.lock:
            self.failures.setdefault(key, []).append(self.clock())


ROUTES = []


def route(method, pattern, auth):
    def register(handler):
        ROUTES.append((method, re.compile("^" + pattern + "$"), auth, handler))
        return handler
    return register


class App:
    def __init__(self, store, whatsapp=None, throttle=None):
        self.store = store
        self.whatsapp = whatsapp  # adapters.whatsapp.WhatsAppAdapter or None (disabled)
        self.throttle = throttle or FailureThrottle(clock=store.clock)

    def __call__(self, environ, start_response):
        try:
            status, body, content_type = self.dispatch(environ)
        except RelayError as exc:
            status, body, content_type = exc.status, {"error": {"code": exc.code, "message": exc.message}}, "application/json"
        except ContractError as exc:
            status, body, content_type = 400, {"error": {"code": "contract_violation", "message": str(exc)}}, "application/json"
        payload = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        reason = {200: "OK", 201: "Created", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
                  405: "Method Not Allowed", 409: "Conflict", 413: "Payload Too Large", 415: "Unsupported Media Type",
                  429: "Too Many Requests"}.get(status, "Error")
        start_response(f"{status} {reason}", [("Content-Type", content_type), ("Content-Length", str(len(payload))),
                                              ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")])
        return [payload]

    def dispatch(self, environ):
        method = environ["REQUEST_METHOD"]
        path = environ.get("PATH_INFO", "")
        raw = self._read(environ) if method == "POST" else b""
        allowed = False
        for route_method, pattern, auth, handler in ROUTES:
            match = pattern.match(path)
            if not match:
                continue
            allowed = True
            if route_method != method:
                continue
            principal = self._auth(environ, auth)
            request = Request(environ, raw, match.groupdict(), principal)
            result = handler(self, request)
            if isinstance(result, tuple) and len(result) == 3:
                return result
            status, body = result if isinstance(result, tuple) else (200, result)
            return status, body, "application/json"
        if allowed:
            raise RelayError(405, "method_not_allowed", "Método no permitido")
        raise RelayError(404, "not_found", "Ruta inexistente")

    @staticmethod
    def _read(environ):
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            raise RelayError(400, "invalid_request", "Content-Length inválido")
        if length > MAX_BODY:
            raise RelayError(413, "too_large", "Cuerpo demasiado grande")
        return environ["wsgi.input"].read(length) if length else b""

    def _auth(self, environ, kind):
        if kind is None:
            return None
        header = environ.get("HTTP_AUTHORIZATION", "")
        token = header[7:].strip() if header.startswith("Bearer ") else ""
        principal = None
        if token and kind == "user" and token.startswith("aku_"):
            user_id = self.store.auth_user(token)
            principal = {"user_id": user_id} if user_id else None
        elif token and kind == "device" and token.startswith("akd_"):
            found = self.store.auth_device(token)
            principal = {"user_id": found[0], "device_id": found[1]} if found else None
        elif token and kind == "viewer" and token.startswith("akr_"):
            found = self.store.auth_viewer(token)
            principal = {"user_id": found[0], "device_id": found[1]} if found else None
        if not principal:
            raise RelayError(401, "unauthorized", "Credencial ausente, inválida o revocada")
        return principal


class Request:
    def __init__(self, environ, raw, args, principal):
        self.environ, self.raw, self.args, self.principal = environ, raw, args, principal

    @property
    def user_id(self):
        return self.principal["user_id"]

    @property
    def device_id(self):
        return self.principal["device_id"]

    def json(self):
        if not self.raw:
            return {}
        if not self.environ.get("CONTENT_TYPE", "").startswith("application/json"):
            raise RelayError(415, "unsupported_media_type", "Usar application/json")
        try:
            body = json.loads(self.raw)
        except (ValueError, UnicodeDecodeError):
            raise RelayError(400, "invalid_json", "JSON inválido")
        if not isinstance(body, dict):
            raise RelayError(400, "invalid_json", "Se esperaba un objeto JSON")
        return body

    def query(self):
        from urllib.parse import parse_qs
        return {k: v[-1] for k, v in parse_qs(self.environ.get("QUERY_STRING", "")).items()}


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# --- public -----------------------------------------------------------------------

@route("GET", "/healthz", None)
def healthz(app, req):
    return {"ok": True, "contract_version": CONTRACT_VERSION}


@route("POST", "/v1/pair", None)
def pair(app, req):
    client = req.environ.get("REMOTE_ADDR", "?")
    if app.throttle.blocked(client):
        raise RelayError(429, "too_many_attempts", "Demasiados intentos; esperar 10 minutos")
    try:
        return 201, app.store.pair_device(req.json().get("code", ""))
    except RelayError:
        app.throttle.fail(client)
        raise


# --- user (phone UI) ----------------------------------------------------------------

@route("GET", "/v1/me", "user")
def me(app, req):
    return {"user_id": req.user_id, "contract_version": CONTRACT_VERSION}


@route("POST", "/v1/devices/pairing-codes", "user")
def pairing_code(app, req):
    return 201, app.store.create_pairing_code(req.user_id, req.json().get("device_name", ""))


@route("GET", "/v1/devices", "user")
def devices(app, req):
    return {"devices": app.store.list_devices(req.user_id)}


@route("POST", r"/v1/devices/(?P<device_id>dev_[0-9a-f]{32})/revoke", "user")
def revoke(app, req):
    return app.store.revoke_device(req.user_id, req.args["device_id"])


@route("POST", "/v1/tasks", "user")
def create_task(app, req):
    body = req.json()
    task, created = app.store.create_task(req.user_id, body.get("client_request_id"), body.get("action"),
                                          body.get("params"), body.get("target_device_id"), channel="api")
    return (201 if created else 200), {"task": task, "deduplicated": not created}


@route("GET", "/v1/tasks", "user")
def list_tasks(app, req):
    q = req.query()
    tasks = app.store.list_tasks(req.user_id, _int(q.get("after_version"), 0), _int(q.get("limit"), 100))
    return {"tasks": tasks, "next_after_version": tasks[-1]["version"] if tasks else _int(q.get("after_version"), 0)}


TASK = r"/v1/tasks/(?P<task_id>tsk_[0-9a-f]{32})"


@route("GET", TASK, "user")
def get_task(app, req):
    return {"task": app.store.get_task(req.user_id, req.args["task_id"], with_events=True)}


@route("POST", TASK + "/approve", "user")
def approve(app, req):
    body = req.json()
    ttl = body.get("ttl_seconds", 24 * 3600)
    return {"task": app.store.approve(req.user_id, req.args["task_id"], body.get("payload_sha256"), ttl)}


@route("POST", TASK + "/reject", "user")
def reject(app, req):
    return {"task": app.store.reject(req.user_id, req.args["task_id"])}


@route("POST", TASK + "/cancel", "user")
def cancel(app, req):
    return {"task": app.store.cancel(req.user_id, req.args["task_id"])}


@route("POST", TASK + "/resolve", "user")
def resolve(app, req):
    body = req.json()
    return {"task": app.store.resolve(req.user_id, req.args["task_id"], body.get("outcome"), body.get("note"))}


@route("POST", TASK + "/retry", "user")
def retry(app, req):
    body = req.json()
    task, created = app.store.retry(req.user_id, req.args["task_id"], body.get("client_request_id"),
                                    body.get("acknowledge_possible_duplicate", False))
    return (201 if created else 200), {"task": task, "deduplicated": not created}


# --- device (Windows agent, outbound only) ------------------------------------------

AGENT_TASK = r"/v1/agent/tasks/(?P<task_id>tsk_[0-9a-f]{32})"


@route("POST", "/v1/agent/claim", "device")
def claim(app, req):
    body = req.json()
    return {"tasks": app.store.claim(req.user_id, req.device_id, _int(body.get("max_tasks"), 1))}


@route("GET", AGENT_TASK, "device")
def agent_task(app, req):
    return {"task": app.store.device_task(req.user_id, req.device_id, req.args["task_id"])}


@route("POST", AGENT_TASK + "/heartbeat", "device")
def heartbeat(app, req):
    return app.store.heartbeat(req.user_id, req.device_id, req.args["task_id"], req.json().get("lease_id"))


@route("POST", AGENT_TASK + "/start", "device")
def start(app, req):
    body = req.json()
    return {"task": app.store.start(req.user_id, req.device_id, req.args["task_id"], body.get("lease_id"), body.get("payload_sha256"))}


@route("POST", AGENT_TASK + "/complete", "device")
def complete(app, req):
    body = req.json()
    return {"task": app.store.complete(req.user_id, req.device_id, req.args["task_id"], body.get("lease_id"),
                                       body.get("outcome"), body.get("result"))}


# --- read-only viewer (PC screen) ---------------------------------------------------

@route("POST", r"/v1/devices/(?P<device_id>dev_[0-9a-f]{32})/viewer-codes", "user")
def viewer_code(app, req):
    return 201, app.store.create_viewer_code(req.user_id, req.args["device_id"])


@route("POST", r"/v1/devices/(?P<device_id>dev_[0-9a-f]{32})/viewer-tokens/revoke", "user")
def viewer_revoke(app, req):
    return app.store.revoke_viewer_tokens(req.user_id, req.args["device_id"])


@route("POST", "/v1/viewer/pair", None)
def viewer_pair(app, req):
    client = req.environ.get("REMOTE_ADDR", "?")
    if app.throttle.blocked(client):
        raise RelayError(429, "too_many_attempts", "Demasiados intentos; esperar 10 minutos")
    try:
        return 201, app.store.pair_viewer(req.json().get("code", ""))
    except RelayError:
        app.throttle.fail(client)
        raise


@route("GET", "/v1/viewer/tasks", "viewer")
def viewer_tasks(app, req):
    q = req.query()
    return app.store.viewer_tasks(req.user_id, req.device_id, _int(q.get("after_version"), 0), _int(q.get("limit"), 200))


# --- WhatsApp (disabled unless configured) -------------------------------------------

@route("GET", "/v1/channels/whatsapp/webhook", None)
def whatsapp_verify(app, req):
    if not app.whatsapp:
        raise RelayError(404, "not_found", "Canal no habilitado")
    challenge = app.whatsapp.verify_subscription(req.query())
    if challenge is None:
        raise RelayError(403, "forbidden", "Token de verificación inválido")
    return 200, challenge.encode(), "text/plain; charset=utf-8"


@route("POST", "/v1/channels/whatsapp/webhook", None)
def whatsapp_webhook(app, req):
    if not app.whatsapp:
        raise RelayError(404, "not_found", "Canal no habilitado")
    if not app.whatsapp.valid_signature(req.raw, req.environ.get("HTTP_X_HUB_SIGNATURE_256", "")):
        raise RelayError(401, "invalid_signature", "Firma inválida")
    try:
        payload = json.loads(req.raw)
    except (ValueError, UnicodeDecodeError):
        raise RelayError(400, "invalid_json", "JSON inválido")
    return {"handled": app.whatsapp.handle(payload)}
