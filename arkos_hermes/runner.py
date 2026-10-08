"""Runs inside Hermes' own Python (one process per request). Reads a request on stdin,
writes one JSON response on stdout. Started by arkos_hermes.bridge with ``python -I -B`` (isolated, no .pyc writes).

Guarantees are enforced in code, not by the prompt:
- AIAgent(enabled_toolsets=[]) and a verified empty tool list before and after the turn;
- provider fixed to Hermes' managed local llama.cpp, no fallback chain;
- non-loopback connections through Python's socket.connect/connect_ex are refused in this
  interpreter (a second layer, not OS isolation: child processes, native code and DNS are
  not covered; see docs/HERMES_BRIDGE.md §3.1);
- user plugins in HERMES_HOME are refused (they would run code at import time).
The runner never reads .env, tokens or the managed runtime state itself: Hermes resolves
its own local endpoint internally.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import sys
import time
from urllib.parse import urlsplit

LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}
SYNTHETIC_ENV = "ARKOS_HERMES_SYNTHETIC_TESTS"


def is_loopback(host):
    if host in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def install_network_guard():
    """Refuse non-loopback socket.connect/connect_ex in this interpreter. Not OS-level isolation."""
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex
    blocked = []

    def check(address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if isinstance(address, tuple) and not is_loopback(str(host)):
            blocked.append(str(host))
            raise ConnectionRefusedError(f"ARKOS bridge: conexión no local bloqueada ({host})")

    def connect(self, address):
        check(address)
        return original(self, address)

    def connect_ex(self, address):
        check(address)
        return original_ex(self, address)

    socket.socket.connect, socket.socket.connect_ex = connect, connect_ex
    return blocked


def hermes_commit(source):
    head = source / ".git" / "HEAD"
    try:
        value = head.read_text(encoding="utf-8").strip()
        if value.startswith("ref: "):
            return (source / ".git" / value[5:]).read_text(encoding="utf-8").strip()
        return value
    except OSError:
        return None


def check_invariants(agent, provider, synthetic):
    problems = []
    if agent.tools:
        problems.append(f"{len(agent.tools)} herramientas cargadas")
    if agent.valid_tool_names:
        problems.append("nombres de herramientas válidos no vacíos")
    if (agent.provider or "").replace(".", "").replace("-", "") != provider.replace(".", "").replace("-", ""):
        problems.append(f"proveedor inesperado: {agent.provider}")
    host = urlsplit(agent.base_url or "").hostname or ""
    if not is_loopback(host):
        problems.append("endpoint no local")
    if getattr(agent, "_fallback_chain", None):
        problems.append("cadena de fallback configurada")
    if getattr(agent, "_fallback_activated", False):
        problems.append("fallback activado")
    if problems:
        raise RuntimeError("; ".join(problems))
    return {"provider": agent.provider, "endpoint": "loopback", "tools_offered": len(agent.tools or [])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes-source", type=Path, required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--synthetic-endpoint", default=None, help="Solo pruebas: endpoint loopback sintético")
    args = parser.parse_args()

    # Hermes may print; keep the real stdout for our single JSON line only.
    out = os.fdopen(os.dup(1), "w", encoding="utf-8")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    request_id = "unknown"

    def emit(body):
        out.write(json.dumps(body, ensure_ascii=False) + "\n")
        out.flush()

    blocked = install_network_guard()
    started = time.monotonic()
    agent = None

    def on_term(signum, frame):
        if agent is not None:
            agent.interrupt("cancelado por ARKOS")
        raise SystemExit(143)
    signal.signal(signal.SIGTERM, on_term)

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from arkos_hermes import contract as c
    try:
        raw = sys.stdin.read(512 * 1024 + 1)
        if len(raw) > 512 * 1024:
            raise c.BridgeError("invalid_request", "Solicitud demasiado grande")
        try:
            request = c.validate_request(json.loads(raw))
        except ValueError as exc:
            if isinstance(exc, c.BridgeError):
                raise
            raise c.BridgeError("invalid_request", "JSON inválido")
        request_id = request["request_id"]

        home = os.environ.get("HERMES_HOME", "")
        if not home or not Path(home).is_dir():
            raise c.BridgeError("unsafe_configuration", "HERMES_HOME explícito requerido")
        plugins = Path(home) / "plugins"
        if plugins.is_dir() and any(plugins.iterdir()):
            raise c.BridgeError("unsafe_configuration", "El perfil del puente no debe tener plugins de usuario")
        os.environ.pop("HERMES_KANBAN_TASK", None)  # would force the kanban toolset back in

        synthetic = args.synthetic_endpoint
        if synthetic:
            if os.environ.get(SYNTHETIC_ENV) != "1" or not is_loopback(urlsplit(synthetic).hostname or ""):
                raise c.BridgeError("unsafe_configuration", "Endpoint sintético solo en pruebas y en loopback")
            provider, kwargs = "custom", {"base_url": synthetic, "api_key": "synthetic-not-a-secret"}
        else:
            provider, kwargs = "llamacpp", {}

        source = args.hermes_source.resolve(strict=True)
        sys.path.insert(0, str(source))
        try:
            from run_agent import AIAgent
        except Exception as exc:
            raise c.BridgeError("runner_failed", f"No se pudo importar Hermes: {type(exc).__name__}")

        starts = []
        try:
            agent = AIAgent(provider=provider, model=args.model, enabled_toolsets=[], skip_memory=True,
                            skip_context_files=True, load_soul_identity=False, quiet_mode=True, fallback_model=None,
                            max_iterations=3, run_budget_seconds=float(request["timeout_s"] - 5),
                            ephemeral_system_prompt=c.SYSTEM_PROMPT, checkpoints_enabled=False,
                            tool_start_callback=lambda *a, **k: starts.append(1), **kwargs)
        except Exception as exc:
            name = type(exc).__name__
            code = "provider_unavailable" if "Provider" in name or "Credential" in name else "runner_failed"
            raise c.BridgeError(code, f"{name}: {str(exc)[:300]}")
        try:
            before = check_invariants(agent, provider, synthetic)
        except RuntimeError as exc:
            raise c.BridgeError("unsafe_configuration", str(exc))

        history = [dict(m) for m in request["messages"][:-1]]
        result = agent.run_conversation(request["messages"][-1]["content"], conversation_history=history or None)
        try:
            check_invariants(agent, provider, synthetic)
        except RuntimeError as exc:
            raise c.BridgeError("unsafe_configuration", "Cambió la configuración durante el turno: " + str(exc))

        attempts = sum(len(m.get("tool_calls") or []) for m in (result.get("messages") or [])
                       if isinstance(m, dict) and m.get("role") == "assistant")
        diagnostics = dict(before, hermes_commit=hermes_commit(source), model=agent.model or None,
                           tool_attempts_blocked=attempts, tool_starts=len(starts), blocked_connections=len(blocked),
                           elapsed_ms=int((time.monotonic() - started) * 1000))
        if starts:
            raise c.BridgeError("unsafe_configuration", "Una herramienta llegó a iniciarse")
        if result.get("interrupted"):
            emit(c.response(request_id, "cancelled", diagnostics=diagnostics, error=("cancelled", "Turno interrumpido")))
            return 0
        if result.get("failed") or result.get("completed") is False:
            message = result.get("error") or result.get("turn_exit_reason") or "El modelo no completó la respuesta"
            emit(c.response(request_id, "error", diagnostics=diagnostics, error=("model_error", message)))
            return 0
        reply, proposals, rejected = c.parse_reply(result.get("final_response") or "")
        if not reply and not proposals:
            raise c.BridgeError("output_invalid", "Respuesta vacía del modelo")
        diagnostics["proposals_rejected"] = rejected
        emit(c.response(request_id, "ok", reply=reply, proposals=proposals, diagnostics=diagnostics))
        return 0
    except c.BridgeError as exc:
        emit(c.response(request_id, "error", diagnostics={"blocked_connections": len(blocked)}, error=(exc.code, exc.message)))
        return 0
    except Exception as exc:  # never leak a traceback to the screen
        emit(c.response(request_id, "error", error=("runner_failed", type(exc).__name__)))
        return 1


if __name__ == "__main__":
    sys.exit(main())
