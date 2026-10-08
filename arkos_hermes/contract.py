"""Bridge contract v1. Pure stdlib: imported both by ARKOS (3.11+) and the Hermes runner (3.14).

The model only *proposes*. A proposal is data for the screen to show; it never enters
arkos_pilot.Queue or the relay by itself, and it carries no approval.
"""
import hashlib
import json
import re

from . import BRIDGE_VERSION

MAX_MESSAGES = 20
MAX_MESSAGE_CHARS = 8000
MAX_HISTORY_CHARS = 32000
MAX_REPLY_CHARS = 8000
MAX_PROPOSALS = 3
MAX_NOTE_CHARS = 20000
MAX_TITLE_CHARS = 120
MIN_TIMEOUT, DEFAULT_TIMEOUT, MAX_TIMEOUT = 10, 120, 300
MAX_STDOUT_BYTES = 1024 * 1024   # enforced while reading; the runner is stopped past it
MAX_STDERR_BYTES = 256 * 1024    # Hermes diagnostics: drained and counted, never stored or shown

STATUSES = ("ok", "error", "timeout", "cancelled")
ERROR_CODES = (
    "invalid_request",        # input violates this contract
    "duplicate_request",      # another request with the same request_id is still active
    "unsafe_configuration",   # tools present, non-local provider, fallback chain or user plugins
    "provider_unavailable",   # managed local llama.cpp not running / not configured
    "model_error",            # Hermes/model failed the turn
    "output_invalid",         # runner produced no parseable response
    "runner_failed",          # runner process crashed or could not start
    "timeout",
    "cancelled",
)
_ID = re.compile(r"^[A-Za-z0-9_.:-]{8,64}$")
# The model is asked to append at most a few blocks like:
#   ```arkos-proposal
#   {"type": "note", "title": "...", "text": "..."}
#   ```
_BLOCK = re.compile(r"```arkos-proposal[ \t]*\n(.*?)\n```", re.DOTALL)

SYSTEM_PROMPT = """Sos ARKOS en modo conversación escrita. No tenés herramientas: no podés ejecutar
comandos, leer ni escribir archivos, navegar, enviar mensajes ni aprobar tareas. Si el usuario
pide algo que requiere actuar, explicá que solo podés proponer una nota para que él la revise.
Respondé en español rioplatense, breve y claro. Si corresponde proponer una nota, agregá al
final, como máximo tres bloques exactamente con este formato:
```arkos-proposal
{"type": "note", "title": "título corto", "text": "contenido de la nota"}
```
Nunca digas que algo fue guardado, aprobado o ejecutado: solo propuesto."""


class BridgeError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def _text(value, limit, label):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
        raise BridgeError("invalid_request", f"{label} vacío, demasiado largo o con caracteres inválidos")
    return value


def validate_request(request):
    """{"v":1,"request_id":str,"messages":[{"role":"user"|"assistant","content":str},...],"timeout_s"?:int}

    The last message must be from the user; earlier ones are prior turns shown on screen.
    """
    if not isinstance(request, dict) or request.get("v") != BRIDGE_VERSION:
        raise BridgeError("invalid_request", "Versión de contrato no soportada")
    if set(request) - {"v", "request_id", "messages", "timeout_s"}:
        raise BridgeError("invalid_request", "Campos inesperados")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not _ID.match(request_id):
        raise BridgeError("invalid_request", "request_id inválido")
    messages = request.get("messages")
    if not isinstance(messages, list) or not 0 < len(messages) <= MAX_MESSAGES:
        raise BridgeError("invalid_request", f"Entre 1 y {MAX_MESSAGES} mensajes")
    total = 0
    clean = []
    for message in messages:
        if not isinstance(message, dict) or set(message) != {"role", "content"} or message["role"] not in ("user", "assistant"):
            raise BridgeError("invalid_request", "Mensaje inválido: solo role user/assistant y content")
        content = _text(message["content"], MAX_MESSAGE_CHARS, "Mensaje")
        total += len(content)
        clean.append({"role": message["role"], "content": content})
    if total > MAX_HISTORY_CHARS:
        raise BridgeError("invalid_request", "Historial demasiado extenso")
    if clean[-1]["role"] != "user":
        raise BridgeError("invalid_request", "El último mensaje debe ser del usuario")
    timeout = request.get("timeout_s", DEFAULT_TIMEOUT)
    if type(timeout) is not int or not MIN_TIMEOUT <= timeout <= MAX_TIMEOUT:
        raise BridgeError("invalid_request", f"timeout_s entre {MIN_TIMEOUT} y {MAX_TIMEOUT}")
    return {"v": BRIDGE_VERSION, "request_id": request_id, "messages": clean, "timeout_s": timeout}


def proposal_digest(proposal):
    body = json.dumps({"type": proposal["type"], "title": proposal["title"], "text": proposal["text"]},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def parse_reply(raw):
    """Split model text into (reply, proposals, rejected_count). Anything not a valid note is dropped."""
    if not isinstance(raw, str):
        return "", [], 0
    proposals, rejected = [], 0
    for block in _BLOCK.findall(raw):
        try:
            data = json.loads(block)
            if (not isinstance(data, dict) or set(data) - {"type", "title", "text"} or data.get("type") != "note"):
                raise ValueError
            text = _text(data.get("text"), MAX_NOTE_CHARS, "Nota")
            title = data.get("title") or text.strip().splitlines()[0]
            if not isinstance(title, str):
                raise ValueError
            title = " ".join(title.split())[:MAX_TITLE_CHARS]
            if len(proposals) >= MAX_PROPOSALS:
                raise ValueError
            proposal = {"type": "note", "title": title, "text": text}
            proposal["proposal_id"] = "prp_" + proposal_digest(proposal)[:24]
            proposal["status"] = "proposed"  # never "approved": approval is a human action elsewhere
            proposals.append(proposal)
        except (ValueError, TypeError, BridgeError):
            rejected += 1
    reply = _BLOCK.sub("", raw).strip()
    if len(reply) > MAX_REPLY_CHARS:
        reply = reply[:MAX_REPLY_CHARS - 1] + "…"
    return reply, proposals, rejected


def response(request_id, status, reply="", proposals=(), diagnostics=None, error=None):
    if status not in STATUSES:
        raise ValueError(status)
    if status != "ok" and (reply or proposals):
        raise ValueError("Una respuesta sin éxito no lleva texto ni propuestas utilizables")
    body = {"v": BRIDGE_VERSION, "request_id": request_id, "status": status, "reply": reply,
            "proposals": list(proposals), "diagnostics": diagnostics or {}}
    if error:
        code, message = error
        body["error"] = {"code": code if code in ERROR_CODES else "runner_failed", "message": str(message)[:500]}
    return body


def validate_response(body, request_id):
    """Parent-side check of what the runner printed; anything off becomes output_invalid."""
    if (not isinstance(body, dict) or body.get("v") != BRIDGE_VERSION or body.get("request_id") != request_id
            or body.get("status") not in STATUSES or not isinstance(body.get("reply"), str)
            or len(body["reply"]) > MAX_REPLY_CHARS or not isinstance(body.get("proposals"), list)
            or len(body["proposals"]) > MAX_PROPOSALS or not isinstance(body.get("diagnostics"), dict)):
        raise BridgeError("output_invalid", "Respuesta del runner inválida")
    for proposal in body["proposals"]:
        if (not isinstance(proposal, dict) or proposal.get("type") != "note" or proposal.get("status") != "proposed"
                or not isinstance(proposal.get("text"), str) or len(proposal["text"]) > MAX_NOTE_CHARS
                or not isinstance(proposal.get("title"), str) or len(proposal["title"]) > MAX_TITLE_CHARS
                or proposal.get("proposal_id") != "prp_" + proposal_digest(proposal)[:24]):
            raise BridgeError("output_invalid", "Propuesta inválida")
    if body["status"] == "ok" and body.get("error"):
        raise BridgeError("output_invalid", "Estado inconsistente")
    if body["status"] != "ok" and (body["reply"] or body["proposals"]):
        # error/timeout/cancelled must never carry text or proposals the screen could use.
        raise BridgeError("output_invalid", "Una respuesta sin éxito no puede traer texto ni propuestas")
    if body["status"] != "ok" and (not isinstance(body.get("error"), dict) or body["error"].get("code") not in ERROR_CODES):
        raise BridgeError("output_invalid", "Error sin código válido")
    return body
