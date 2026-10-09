"""ARKOS side of the bridge: one isolated Hermes process per request, with timeout and cancel.

This module never imports Hermes and never writes to arkos_pilot.Queue or the relay. A reply
and its note proposals are returned to the caller (the screen) for human review.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time

from . import contract as c

RUNNER = Path(__file__).with_name("runner.py")
# Variables a Windows/Python process needs; provider keys and tokens are not forwarded.
PASSTHROUGH_ENV = ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "TEMP", "TMP",
                   "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME", "LOCALAPPDATA", "APPDATA", "LANG", "LC_ALL")


class _Run:
    """State of one in-flight request; cancel and overflow flags never leak across runs."""

    def __init__(self):
        self.lock = threading.Lock()
        self.process = None
        self.cancelled = False
        self.overflow = None
        self.stdout = bytearray()


class HermesBridge:
    def __init__(self, hermes_python, hermes_source, hermes_home, model="", runner=RUNNER, synthetic_endpoint=None):
        self.hermes_python = str(hermes_python)
        self.hermes_source = Path(hermes_source)
        self.hermes_home = Path(hermes_home)
        self.model = model or ""
        self.runner = Path(runner)
        self.synthetic_endpoint = synthetic_endpoint
        self._active = {}
        self._lock = threading.Lock()

    def _command(self):
        command = [self.hermes_python, "-I", "-B", str(self.runner), "--hermes-source", str(self.hermes_source)]
        if self.model:
            command += ["--model", self.model]
        if self.synthetic_endpoint:
            command += ["--synthetic-endpoint", self.synthetic_endpoint]
        return command

    def _env(self):
        env = {k: os.environ[k] for k in PASSTHROUGH_ENV if k in os.environ}
        env.update(HERMES_HOME=str(self.hermes_home), PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        if self.synthetic_endpoint and os.environ.get("ARKOS_HERMES_SYNTHETIC_TESTS") == "1":
            env["ARKOS_HERMES_SYNTHETIC_TESTS"] = "1"
        return env

    def converse(self, request, cancel_event=None):
        """Returns a contract response dict. Never raises for runtime problems."""
        try:
            request = c.validate_request(request)
        except c.BridgeError as exc:
            rid = request.get("request_id") if isinstance(request, dict) and isinstance(request.get("request_id"), str) else "invalid"
            return c.response(rid[:64], "error", error=(exc.code, exc.message))
        request_id = request["request_id"]
        run = _Run()
        with self._lock:
            # One live request per id: a duplicate must never share, replace or cancel another run.
            if request_id in self._active:
                return c.response(request_id, "error", error=("duplicate_request", "Ya hay un pedido activo con ese request_id"))
            self._active[request_id] = run
        try:
            return self._execute(request, run, cancel_event)
        finally:
            with self._lock:
                if self._active.get(request_id) is run:
                    del self._active[request_id]

    def _execute(self, request, run, cancel_event=None):
        request_id = request["request_id"]
        started = time.monotonic()
        # Empty working directory: Hermes probes the cwd (git, AGENTS.md); give it nothing to read.
        with tempfile.TemporaryDirectory(prefix="arkos-hermes-") as cwd:
            with run.lock:
                if run.cancelled or (cancel_event is not None and cancel_event.is_set()):
                    return c.response(request_id, "cancelled", error=("cancelled", "Cancelado por el usuario"))
                try:
                    run.process = subprocess.Popen(self._command(), cwd=cwd, env=self._env(), stdin=subprocess.PIPE,
                                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                except OSError as exc:
                    return c.response(request_id, "error", error=("runner_failed", f"No se pudo iniciar Hermes: {type(exc).__name__}"))
            process = run.process
            payload = json.dumps(request).encode("utf-8")
            threads = [threading.Thread(target=self._write_stdin, args=(process, payload), daemon=True),
                       threading.Thread(target=self._read_limited, args=(run, process.stdout, "stdout", c.MAX_STDOUT_BYTES), daemon=True),
                       threading.Thread(target=self._read_limited, args=(run, process.stderr, "stderr", c.MAX_STDERR_BYTES), daemon=True)]
            for thread in threads:
                thread.start()
            timed_out = False
            deadline = time.monotonic() + request["timeout_s"]
            while process.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    run.cancelled = True
                    self._kill(process)
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    self._kill(process)
                    break
                try:
                    process.wait(timeout=min(.05, remaining))
                except subprocess.TimeoutExpired:
                    pass
            for thread in threads:
                thread.join(timeout=10)
            for stream in (process.stdin, process.stdout, process.stderr):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass
        elapsed = {"elapsed_ms": int((time.monotonic() - started) * 1000)}
        if run.cancelled:
            return c.response(request_id, "cancelled", diagnostics=elapsed, error=("cancelled", "Cancelado por el usuario"))
        if run.overflow:
            return c.response(request_id, "error", diagnostics=elapsed,
                              error=("output_invalid", f"El runner excedió el presupuesto de {run.overflow}; se detuvo"))
        if timed_out:
            return c.response(request_id, "timeout", diagnostics=elapsed, error=("timeout", f"Sin respuesta en {request['timeout_s']} s"))
        try:
            lines = [line for line in bytes(run.stdout).decode("utf-8").splitlines() if line.strip()]
            if len(lines) != 1:
                raise c.BridgeError("output_invalid", "Se esperaba una sola respuesta JSON")
            return c.validate_response(json.loads(lines[0]), request_id)
        except (ValueError, UnicodeDecodeError) as exc:
            code = exc.code if isinstance(exc, c.BridgeError) else "output_invalid"
            return c.response(request_id, "error", error=(code, "Respuesta inválida del runner"))

    @staticmethod
    def _write_stdin(process, payload):
        try:
            process.stdin.write(payload)
            process.stdin.close()
        except (OSError, ValueError):
            pass  # runner exited or was killed before reading everything

    def _read_limited(self, run, stream, name, limit):
        """Read in chunks; past the budget, stop the process instead of buffering more."""
        kept = run.stdout if name == "stdout" else None
        total = 0
        while True:
            try:
                chunk = stream.read1(65536) if hasattr(stream, "read1") else stream.read(65536)
            except (OSError, ValueError):
                return
            if not chunk:
                return
            total += len(chunk)
            if total > limit:
                with run.lock:
                    run.overflow = run.overflow or name
                self._kill(run.process)
                return
            if kept is not None:
                kept.extend(chunk)  # stderr is drained and counted, never kept or shown

    def cancel(self, request_id):
        """Stop the run registered under this id only. Returns False if none is active."""
        with self._lock:
            run = self._active.get(request_id)
        if run is None:
            return False
        with run.lock:
            run.cancelled = True
            process = run.process
        if process is not None:
            self._kill(process)
        return True

    @staticmethod
    def _kill(process):
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
