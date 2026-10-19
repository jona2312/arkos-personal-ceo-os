"""Client-side Cloud adapter: implements arkos_pilot.providers.ConversationProvider.

Runs on the PC and speaks only to the ARKOS gateway through an injected transport. It
holds a revocable ARKOS device token (akc_), never a provider key. One converse() makes at
most one gateway request; a lost or late answer is reported as outcome_uncertain and is
never retried automatically. Not registered in the selector: 'cloud' stays rejected.
"""
import json
import re
import threading
import time

from arkos_hermes import contract as c
from .gateway import TOKEN

MAX_RESPONSE_BYTES = 256 * 1024
POLL_S = 0.05
_RID = re.compile(r"^[A-Za-z0-9_.:-]{8,64}$")


class TransportNotSent(Exception):
    """The request provably did not reach the gateway (e.g. connection refused, DNS failure)."""


class CloudConversationProvider:
    def __init__(self, config, consent, transport, device_token):
        """transport.request(method, path, headers, body_bytes, timeout_s) -> (status, body_bytes).

        It raises TransportNotSent when nothing left the PC; any other exception means unknown.
        """
        if not isinstance(device_token, str) or not TOKEN.match(device_token):
            raise ValueError("Token de dispositivo ARKOS inválido (se espera akc_…; nunca una clave del proveedor)")
        self.config, self.consent, self.transport = config, consent, transport
        self._token = device_token

    def __repr__(self):
        return f"CloudConversationProvider(gateway={self.config.gateway_url!r})"

    def _headers(self, request_id=None, json_body=False):
        headers = {"Authorization": "Bearer " + self._token,
                   "X-Arkos-Consent": self.config.disclosure.digest()}
        if json_body:
            headers["Content-Type"] = "application/json"
        if request_id:
            headers["Idempotency-Key"] = request_id
        return headers

    def converse(self, request, cancel_event=None):
        try:
            request = c.validate_request(request)
        except c.BridgeError as exc:
            rid = request.get("request_id") if isinstance(request, dict) else None
            return _error(rid, exc.code, exc.message)
        rid = request["request_id"]
        if sum(len(m["content"]) for m in request["messages"]) > self.config.disclosure.max_input_chars:
            return _error(rid, "invalid_request", "La conversación supera el límite de entrada Cloud")
        # Consent is checked here, before any byte leaves; the gateway checks it again.
        if not self.consent.valid_for(self.config.disclosure):
            return _error(rid, "consent_required", "Cloud requiere consentimiento vigente; no se envió nada")
        if cancel_event is not None and cancel_event.is_set():
            return c.response(rid, "cancelled", error=("cancelled", "Cancelado antes de enviar"))

        timeout = min(request["timeout_s"], self.config.timeout_s)
        body = json.dumps(request, ensure_ascii=False).encode("utf-8")
        outcome = {}

        def send():
            try:
                outcome["value"] = self.transport.request("POST", "/v1/conversations",
                                                          self._headers(rid, json_body=True), body, timeout)
            except TransportNotSent:
                outcome["not_sent"] = True
            except Exception:  # noqa: BLE001 - every other failure is "unknown", by design
                outcome["lost"] = True

        worker = threading.Thread(target=send, daemon=True, name="arkos-cloud-" + rid)
        worker.start()
        deadline = time.monotonic() + timeout + 1
        while worker.is_alive():
            if cancel_event is not None and cancel_event.is_set():
                self._cancel_remote(rid)
                # A late gateway answer lands in `outcome`, which nobody reads any more.
                return c.response(rid, "cancelled", error=("cancelled", "Cancelado por el usuario"))
            if time.monotonic() > deadline:
                self._cancel_remote(rid)  # stop further spend; the outcome stays uncertain
                return c.response(rid, "timeout", error=("outcome_uncertain",
                                  "Sin respuesta a tiempo; resultado incierto, no se reintenta"))
            worker.join(POLL_S)
        if cancel_event is not None and cancel_event.is_set():
            return c.response(rid, "cancelled", error=("cancelled", "Cancelado por el usuario"))
        if outcome.get("not_sent"):
            return _error(rid, "provider_unavailable", "No se pudo contactar al gateway ARKOS Cloud; no se envió nada")
        if "value" not in outcome:
            return _error(rid, "outcome_uncertain", "Se perdió la respuesta; resultado incierto, no se reintenta")
        return self._interpret(rid, *outcome["value"])

    def _interpret(self, rid, status, raw):
        try:
            if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError
            data = json.loads(bytes(raw).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            # The gateway may have reserved and called the provider: unknown, not "failed".
            return _error(rid, "outcome_uncertain", "Respuesta del gateway ilegible; resultado incierto")
        if status in (200, 400, 409, 412, 429) and isinstance(data, dict) and "status" in data:
            try:
                body = c.validate_response(data, rid)
            except c.BridgeError:
                return _error(rid, "outcome_uncertain", "Respuesta del gateway inválida; resultado incierto")
            # Only display fields leave the adapter; diagnostics stay minimal and declared.
            return {**{k: body[k] for k in ("v", "request_id", "status", "reply", "proposals")},
                    "diagnostics": {"processing": "cloud"}, **({"error": body["error"]} if "error" in body else {})}
        if status == 401:
            return _error(rid, "unsafe_configuration", "Token de dispositivo rechazado por el gateway")
        if status in (413, 415):
            return _error(rid, "invalid_request", "El gateway rechazó el pedido")
        return _error(rid, "outcome_uncertain", f"Estado inesperado del gateway ({int(status) if isinstance(status, int) else '?'})")

    def _cancel_remote(self, rid):
        """Best effort; cancelling cannot undo what the provider may already have processed."""
        def run():
            try:
                self.transport.request("POST", f"/v1/conversations/{rid}/cancel", self._headers(), b"", 10)
            except Exception:  # noqa: BLE001
                pass
        threading.Thread(target=run, daemon=True).start()

    def gateway_status(self, timeout_s=5):
        """Gateway disclosure digest and provider mode ('test'|'real'). None if unreachable or invalid."""
        try:
            status, raw = self.transport.request("GET", "/v1/status", self._headers(), b"", timeout_s)
            if status != 200 or not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_RESPONSE_BYTES:
                return None
            data = json.loads(bytes(raw).decode("utf-8"))
        except Exception:  # noqa: BLE001 - unreachable gateway is a normal state for the screen
            return None
        if (not isinstance(data, dict) or not isinstance(data.get("disclosure_digest"), str)
                or data.get("provider_mode") not in ("test", "real")):
            return None
        terms, trial = data.get("terms_digest"), data.get("trial")
        trial = ({k: trial.get(k) for k in ("name", "limit_micro_usd", "charged_micro_usd", "open_micro_usd",
                                            "remaining_micro_usd")} if isinstance(trial, dict) else None)
        return {"disclosure_digest": data["disclosure_digest"], "provider_mode": data["provider_mode"],
                "terms_digest": terms if isinstance(terms, str) else None, "trial": trial}

    def lookup(self, request_id):
        """Explicit human 'check status' action: reads billing state; never triggers a call."""
        if not isinstance(request_id, str) or not _RID.match(request_id):
            raise ValueError("request_id inválido")
        status, raw = self.transport.request("GET", f"/v1/conversations/{request_id}", self._headers(), b"", 10)
        if status != 200 or not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_RESPONSE_BYTES:
            return None
        data = json.loads(bytes(raw).decode("utf-8"))
        return {k: data[k] for k in ("request_id", "state", "reserved_micro_usd", "charged_micro_usd") if k in data}


def _error(rid, code, message):
    rid = rid if isinstance(rid, str) and _RID.match(rid) else "invalid"
    return c.response(rid, "error", error=(code, message))
