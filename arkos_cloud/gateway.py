"""ARKOS Cloud gateway: the only component that talks to the paid provider.

Holds the provider transport (and therefore the provider credential) server-side. For each
request: authenticate the ARKOS token -> require the consent digest of the current
disclosure -> enforce input limits -> idempotency by (user, request_id) -> reserve the
worst-case cost -> commit 'sent' -> one provider call -> settle. It never retries a call
and never approves or executes anything: proposals are returned as data only.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time

from arkos_hermes import contract as c
from .ledger import Ledger, LedgerError, token_hash

MAX_BODY_BYTES = 256 * 1024
TOKEN = re.compile(r"^akc_[A-Za-z0-9_-]{32,128}$")
_RID = re.compile(r"^[A-Za-z0-9_.:-]{8,64}$")
_PATH = re.compile(r"^/v1/conversations(?:/([A-Za-z0-9_.:-]{8,64})(/cancel)?)?$")


@dataclass(frozen=True)
class ProviderResult:
    text: str
    input_tokens: int | None
    output_tokens: int | None


class ProviderNotSent(Exception):
    """The request provably never left (e.g. connection refused): nothing to pay."""


class ProviderRejected(Exception):
    """The provider answered with a definite, non-billable refusal (e.g. 400/401/429)."""


class ProviderLost(Exception):
    """Sent, but the outcome is unknown (timeout, reset). Kept uncertain; never retried."""


class InstanceLock:
    """Exclusive OS lock on '<ledger>.lock' for the gateway's lifetime.

    The ledger assumes a single gateway: recovery turns another instance's in-flight calls
    into 'uncertain'. A second gateway on the same file fails here, before touching it.
    Valid on a local disk of a single host; network file systems are not supported.
    """

    def __init__(self, ledger_path):
        self.path = Path(str(ledger_path) + ".lock")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            raise RuntimeError("Otra instancia del gateway ya usa este ledger; no se inicia una segunda.")

    def release(self):
        if self.handle.closed:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()


def request_digest(request):
    raw = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def utc_day(now=None):
    return time.strftime("%Y-%m-%d", time.gmtime(now))


class CloudGateway:
    def __init__(self, config, ledger_path, provider, token_hashes=None, clock=time.time):
        """token_hashes: optional {sha256(akc_ token): user_id} to register (persisted, hash only).

        Tokens live in the ledger and are checked on every request, so revoking one with
        Ledger.revoke_token (operator CLI) takes effect without a restart.
        """
        self.config, self.provider, self.clock = config, provider, clock
        self._instance = InstanceLock(ledger_path)
        try:
            self.ledger = Ledger(ledger_path)
            for digest, user in (token_hashes or {}).items():
                self.ledger.register_token_hash(digest, user)
            self.ledger.recover()
        except BaseException:
            self._instance.release()
            raise
        self._cancel = {}
        self._lock = threading.Lock()

    def close(self):
        try:
            self.ledger.close()
            if callable(getattr(self.provider, "close", None)):
                self.provider.close()
        finally:
            self._instance.release()

    # --- cost ---------------------------------------------------------------
    def input_bound(self, request):
        """Assumed upper bound on billable input tokens: one per UTF-8 byte, plus framing.

        Holds for byte-level BPE tokenizers; staging must confirm it against usage reports
        (an excess is recorded as overrun). No prompt caching is used, so no cache writes.
        """
        text = c.SYSTEM_PROMPT + "".join(m["content"] for m in request["messages"])
        return len(text.encode("utf-8")) + 16 * len(request["messages"]) + 64

    def reservation(self, request):
        """Worst case: the input bound plus max_output_tokens (which includes any thinking)."""
        return self._cost(self.input_bound(request), self.config.disclosure.max_output_tokens)

    def _cost(self, tokens_in, tokens_out):
        cfg = self.config
        long = cfg.long_context_threshold_tokens and tokens_in > cfg.long_context_threshold_tokens
        price_in = cfg.long_input_micro_usd_per_mtok if long else cfg.input_micro_usd_per_mtok
        price_out = cfg.long_output_micro_usd_per_mtok if long else cfg.output_micro_usd_per_mtok
        return math.ceil(tokens_in * price_in / 1_000_000) + math.ceil(tokens_out * price_out / 1_000_000)

    # --- API ----------------------------------------------------------------
    def authenticate(self, headers):
        auth = headers.get("authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if not TOKEN.match(token):
            return None
        return self.ledger.user_for(token_hash(token))

    def converse(self, user, consent, body):
        """Returns (http_status, json_body)."""
        hint = body.get("request_id") if isinstance(body, dict) else None
        hint = hint if isinstance(hint, str) and _RID.match(hint) else "invalid"
        if consent != self.config.disclosure.digest():
            return 412, _error(hint, "consent_required", "Falta consentimiento vigente para esta configuración")
        try:
            request = c.validate_request(body)
        except c.BridgeError as exc:
            return 400, _error(hint, exc.code, exc.message)
        rid = request["request_id"]
        if sum(len(m["content"]) for m in request["messages"]) > self.config.disclosure.max_input_chars:
            return 400, _error(rid, "invalid_request", "La conversación supera el límite de entrada Cloud")
        digest = request_digest(request)
        amount = self.reservation(request)
        retention_s = self.config.disclosure.gateway_retention_hours * 3600
        self.ledger.purge_content(retention_s)
        try:
            created, row = self.ledger.reserve(user, rid, digest, amount, utc_day(self.clock()),
                                               self.config.per_user_daily_micro_usd, self.config.global_daily_micro_usd,
                                               self.config.global_monthly_micro_usd)
        except LedgerError as exc:
            status = {"conflict": 409, "busy": 409, "budget_exhausted": 429}[exc.code]
            code = "budget_exhausted" if exc.code == "budget_exhausted" else "duplicate_request"
            return status, _error(rid, code, str(exc))
        if not created:
            return 200, self._replay(row)
        event = threading.Event()
        with self._lock:
            self._cancel[(user, rid)] = event
        try:
            return 200, self._call(user, request, event)
        finally:
            with self._lock:
                self._cancel.pop((user, rid), None)

    def _replay(self, row):
        """Same request again: never a second provider call."""
        rid = row["request_id"]
        if row["state"] == "completed":
            if row["response"]:
                return row["response"]
            return _error(rid, "duplicate_request", "Ese pedido ya se respondió y su contenido expiró")
        if row["state"] in ("failed",):
            return _error(rid, "provider_unavailable", "Ese pedido falló sin consumo; usá un pedido nuevo")
        if row["state"] == "cancelled":
            return c.response(rid, "cancelled", error=("cancelled", "Pedido cancelado"))
        return _error(rid, "outcome_uncertain", "Resultado incierto; no se repite automáticamente")

    def _call(self, user, request, event):
        rid = request["request_id"]
        if not self.ledger.mark_sent(user, rid):
            return c.response(rid, "cancelled", error=("cancelled", "Cancelado antes de enviar"))
        reserved = self.ledger.get(user, rid)["reserved"]
        try:
            result = self.provider.complete(system=c.SYSTEM_PROMPT, messages=request["messages"],
                                            max_output_tokens=self.config.disclosure.max_output_tokens,
                                            timeout_s=request["timeout_s"], cancel_event=event)
        except (ProviderNotSent, ProviderRejected):
            row = self._settle(user, rid, "not_charged")
            if row is not None and row["state"] == "cancelled":
                return c.response(rid, "cancelled", error=("cancelled", "Pedido cancelado"))
            return _error(rid, "provider_unavailable", "El proveedor Cloud rechazó o no recibió el pedido")
        except Exception:  # ProviderLost or anything unexpected: may have been billed
            self._settle(user, rid, "uncertain")
            return _error(rid, "outcome_uncertain", "Resultado incierto; no se repite automáticamente")
        if not isinstance(result, ProviderResult) or not isinstance(result.text, str):
            self._settle(user, rid, "uncertain")
            return _error(rid, "outcome_uncertain", "Respuesta del proveedor ilegible")
        known = (type(result.input_tokens) is int and type(result.output_tokens) is int
                 and result.input_tokens >= 0 and result.output_tokens >= 0)
        charged = self._cost(result.input_tokens, result.output_tokens) if known else reserved
        if len(result.text) > self.config.disclosure.max_output_tokens * 16:
            self._settle(user, rid, "completed", charged=charged)
            return _error(rid, "output_invalid", "La salida excedió el límite configurado")
        reply, proposals, rejected = c.parse_reply(result.text)
        if not reply and not proposals:
            body = _error(rid, "output_invalid", "Respuesta vacía del proveedor")
        else:
            body = c.response(rid, "ok", reply=reply, proposals=proposals,
                              diagnostics={"processing": "cloud", "proposals_rejected": rejected,
                                           "charged_micro_usd": charged, "usage_known": known})
        keep = body["status"] == "ok" and self.config.disclosure.gateway_retention_hours > 0
        row = self._settle(user, rid, "completed", charged=charged, response=body if keep else None)
        if row is None:
            return _error(rid, "outcome_uncertain", "No se pudo registrar el resultado")
        if row["state"] == "cancelled":
            return c.response(rid, "cancelled", error=("cancelled", "Pedido cancelado"))
        return body

    def _settle(self, user, rid, outcome, **kwargs):
        try:
            return self.ledger.settle(user, rid, outcome, **kwargs)
        except LedgerError:
            return None

    @property
    def provider_mode(self):
        """'test' only for providers that declare it (local fakes); anything else counts as real."""
        return "test" if getattr(self.provider, "mode", "real") == "test" else "real"

    def status(self):
        """What the PC must check before activation: same disclosure, and test vs real provider."""
        return {"disclosure_digest": self.config.disclosure.digest(), "disclosure": self.config.disclosure.as_dict(),
                "provider_mode": self.provider_mode}

    def cancel(self, user, rid):
        row = self.ledger.request_cancel(user, rid, day=utc_day(self.clock()))
        with self._lock:
            event = self._cancel.get((user, rid))
        if event:
            event.set()
        return 200, _state(row)

    def lookup(self, user, rid):
        row = self.ledger.get(user, rid)
        if row is None:
            return 404, {"error": {"code": "not_found"}}
        return 200, _state(row)

    def dispatch(self, method, path, headers, body):
        """HTTP-shaped entry point for a future server. headers: lower-case names."""
        headers = {str(k).lower(): str(v) for k, v in headers.items()}
        user = self.authenticate(headers)
        if user is None:
            return 401, {"error": {"code": "unauthorized"}}
        if path == "/v1/status":
            if method != "GET":
                return 405, {"error": {"code": "invalid_request"}}
            return 200, self.status()
        match = _PATH.match(path)
        if not match:
            return 404, {"error": {"code": "not_found"}}
        if not isinstance(body, (bytes, bytearray)) or len(body) > MAX_BODY_BYTES:
            return 413, {"error": {"code": "invalid_request"}}
        rid, cancel = match.groups()
        if method == "POST" and rid is None:
            if headers.get("content-type", "").split(";")[0].strip() != "application/json":
                return 415, {"error": {"code": "invalid_request"}}
            try:
                data = json.loads(bytes(body).decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                return 400, {"error": {"code": "invalid_request"}}
            if not isinstance(data, dict) or headers.get("idempotency-key") != data.get("request_id"):
                return 400, {"error": {"code": "invalid_request"}}
            return self.converse(user, headers.get("x-arkos-consent", ""), data)
        if method == "POST" and cancel:
            return self.cancel(user, rid)
        if method == "GET" and rid and not cancel:
            return self.lookup(user, rid)
        return 405, {"error": {"code": "invalid_request"}}


def _error(rid, code, message):
    return c.response(rid if isinstance(rid, str) and rid else "invalid", "error", error=(code, message))


def _state(row):
    """Status for a human 'check' action: billing state only, never a new call."""
    body = {"request_id": row["request_id"], "state": row["state"],
            "reserved_micro_usd": row["reserved"], "charged_micro_usd": row["charged"]}
    if row["state"] == "completed" and row.get("response"):
        body["response"] = row["response"]
    return body
