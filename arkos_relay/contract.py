"""Shared contract: actions, canonical digest, task states.

Every client (phone UI, WhatsApp adapter, Windows agent) must compute the same
digest for the same action. Canonical form: UTF-8 JSON, keys sorted, no
whitespace, integers only (no floats), so it is reproducible from JavaScript
with a sorted-keys JSON.stringify.
"""
import hashlib
import json
import re

from . import CONTRACT_VERSION

# Task lifecycle. Terminal states never change again except unknown -> resolved.
AWAITING_APPROVAL = "awaiting_approval"
APPROVED = "approved"
CLAIMED = "claimed"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
UNKNOWN = "unknown"
REJECTED = "rejected"
CANCELLED = "cancelled"

STATES = (AWAITING_APPROVAL, APPROVED, CLAIMED, RUNNING, SUCCEEDED, FAILED, UNKNOWN, REJECTED, CANCELLED)
TERMINAL = (SUCCEEDED, FAILED, REJECTED, CANCELLED)
CANCELLABLE = (AWAITING_APPROVAL, APPROVED, CLAIMED)
# Outcomes a device may report. "failed" means: no effect was produced.
DEVICE_OUTCOMES = (SUCCEEDED, FAILED, UNKNOWN)

MAX_APPROVAL_SECONDS = 24 * 3600
MAX_TEXT = 100_000
MAX_DOCUMENT = 200_000
MAX_MS = 24 * 3600 * 1000

_ID = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")
_ROOT = re.compile(r"^[a-z0-9_-]{1,32}$")
_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}\.(md|txt)$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ContractError(ValueError):
    """Input does not satisfy the shared contract."""


def canonical(value):
    _reject_floats(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _reject_floats(value):
    if isinstance(value, float):
        raise ContractError("Solo se admiten enteros en el contrato (usar milisegundos)")
    if isinstance(value, dict):
        for item in value.values():
            _reject_floats(item)
    elif isinstance(value, list):
        for item in value:
            _reject_floats(item)


def task_digest(action, params, target_device_id):
    """Digest that an approval is bound to: exact action, parameters and target."""
    body = {"v": CONTRACT_VERSION, "action": action, "params": params, "target_device_id": target_device_id}
    return hashlib.sha256(canonical(body)).hexdigest()


def _is_int(value):
    return type(value) is int


def _text(value, limit, label):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ContractError(f"{label} vacío o demasiado extenso")
    if "\x00" in value:
        raise ContractError(f"{label} contiene caracteres no válidos")


def _keys(params, required, optional=()):
    if not isinstance(params, dict):
        raise ContractError("params debe ser un objeto")
    keys = set(params)
    if not set(required) <= keys or not keys <= set(required) | set(optional):
        raise ContractError("Parámetros inesperados o incompletos")


def relative_path(value):
    """Relative path under a root alias configured on the PC; never absolute."""
    if not isinstance(value, str) or not 0 < len(value) <= 260 or "\x00" in value:
        raise ContractError("Ruta inválida")
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if normalized.startswith("/") or ":" in normalized or any(p in ("", ".", "..") for p in parts):
        raise ContractError("La ruta debe ser relativa a una carpeta autorizada, sin '..'")
    return "/".join(parts)


def validate_action(action, params):
    """Allow-list of v1 actions. Anything else, including commands, is refused."""
    if action == "note.create":
        _keys(params, ("text",))
        _text(params["text"], MAX_TEXT, "Nota")
    elif action == "document.create":
        _keys(params, ("filename", "text"))
        if not isinstance(params["filename"], str) or not _FILENAME.match(params["filename"]):
            raise ContractError("Nombre de documento inválido (.md o .txt, sin rutas)")
        _text(params["text"], MAX_DOCUMENT, "Documento")
    elif action == "video.clip":
        _keys(params, ("root", "path", "start_ms", "duration_ms"), ("source_sha256",))
        if not isinstance(params["root"], str) or not _ROOT.match(params["root"]):
            raise ContractError("Carpeta autorizada inválida")
        if relative_path(params["path"]) != params["path"]:
            raise ContractError("Usar '/' como separador de ruta")
        for key in ("start_ms", "duration_ms"):
            if not _is_int(params[key]) or not 0 <= params[key] <= MAX_MS:
                raise ContractError("Tiempos inválidos")
        if params["duration_ms"] == 0:
            raise ContractError("La duración debe ser positiva")
        if "source_sha256" in params and not (isinstance(params["source_sha256"], str) and _HEX64.match(params["source_sha256"])):
            raise ContractError("Huella del archivo inválida")
    else:
        raise ContractError("Acción no soportada; no se ejecutan comandos arbitrarios")


def validate_id(value, label="id"):
    if not isinstance(value, str) or not _ID.match(value):
        raise ContractError(f"{label} inválido (8-128 caracteres [A-Za-z0-9_.:-])")
    return value


def validate_result(result):
    """Results carry metadata, never file contents or absolute paths."""
    if result is None:
        return {}
    if not isinstance(result, dict) or not set(result) <= {"message", "output"}:
        raise ContractError("Resultado inválido")
    if "message" in result and (not isinstance(result["message"], str) or len(result["message"]) > 2000):
        raise ContractError("Mensaje de resultado inválido")
    output = result.get("output")
    if output is not None:
        if not isinstance(output, dict) or set(output) - {"name", "sha256", "bytes", "source_sha256"}:
            raise ContractError("Salida inválida")
        name = output.get("name")
        if not isinstance(name, str) or not 0 < len(name) <= 200 or "/" in name or "\\" in name:
            raise ContractError("Nombre de salida inválido")
        for key in ("sha256", "source_sha256"):
            if key in output and not (isinstance(output[key], str) and _HEX64.match(output[key])):
                raise ContractError("Huella de salida inválida")
        if "bytes" in output and (not _is_int(output["bytes"]) or output["bytes"] < 0):
            raise ContractError("Tamaño de salida inválido")
    canonical(result)
    return result
