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

    def converse(self, request):
        """Returns a contract response dict. Never raises for runtime problems."""
        try:
            request = c.validate_request(request)
        except c.BridgeError as exc:
            rid = request.get("request_id") if isinstance(request, dict) and isinstance(request.get("request_id"), str) else "invalid"
            return c.response(rid[:64], "error", error=(exc.code, exc.message))
        request_id = request["request_id"]
        started = time.monotonic()
        # Empty working directory: Hermes probes the cwd (git, AGENTS.md); give it nothing to read.
        with tempfile.TemporaryDirectory(prefix="arkos-hermes-") as cwd:
            try:
                process = subprocess.Popen(self._command(), cwd=cwd, env=self._env(), stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except OSError as exc:
                return c.response(request_id, "error", error=("runner_failed", f"No se pudo iniciar Hermes: {type(exc).__name__}"))
            with self._lock:
                self._active[request_id] = process
            try:
                stdout, _stderr = process.communicate(json.dumps(request).encode("utf-8"), timeout=request["timeout_s"])
            except subprocess.TimeoutExpired:
                self._kill(process)
                process.communicate()  # drain and close the pipes of the killed runner
                return c.response(request_id, "timeout", diagnostics={"elapsed_ms": int((time.monotonic() - started) * 1000)},
                                  error=("timeout", f"Sin respuesta en {request['timeout_s']} s"))
            finally:
                with self._lock:
                    cancelled = self._active.pop(request_id, None) is None
            if cancelled:
                return c.response(request_id, "cancelled", error=("cancelled", "Cancelado por el usuario"))
        try:
            if len(stdout) > c.MAX_STDOUT_BYTES:
                raise c.BridgeError("output_invalid", "Salida demasiado grande")
            lines = [line for line in stdout.decode("utf-8").splitlines() if line.strip()]
            if len(lines) != 1:
                raise c.BridgeError("output_invalid", "Se esperaba una sola respuesta JSON")
            return c.validate_response(json.loads(lines[0]), request_id)
        except (ValueError, UnicodeDecodeError) as exc:
            code = exc.code if isinstance(exc, c.BridgeError) else "output_invalid"
            return c.response(request_id, "error", error=(code, "Respuesta inválida del runner"))

    def cancel(self, request_id):
        """Stop a running request. The process is killed; nothing it produced is used."""
        with self._lock:
            process = self._active.pop(request_id, None)
        if process is None:
            return False
        self._kill(process)
        return True

    @staticmethod
    def _kill(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
