"""Windows agent: outbound-only sync with the relay and allow-listed local execution.

Order per task (journaled locally before each network step):
  claimed -> start_sent -> running -> done_local -> reported
After a crash nothing is executed again: start_sent means no effect yet; running
without done_local means the outcome is checked against the expected output or
reported as unknown.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
from urllib import error, request
from urllib.parse import urlsplit

from arkos_pilot import core as pilot
from . import contract as c


class TransportError(Exception):
    """Network failure: the request may or may not have reached the server."""


class ApiError(Exception):
    def __init__(self, status, code, message=""):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code = status, code


class HttpTransport:
    def __init__(self, base_url, token, timeout=30, allow_insecure_localhost=False):
        parts = urlsplit(base_url)
        local = parts.hostname in ("127.0.0.1", "localhost", "::1")
        if parts.scheme != "https" and not (allow_insecure_localhost and local and parts.scheme == "http"):
            raise ValueError("El servidor debe usar HTTPS")
        self.base_url, self.token, self.timeout = base_url.rstrip("/"), token, timeout

    def __call__(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = request.Request(self.base_url + path, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read() or b"{}")
        except error.HTTPError as exc:
            try:
                detail = json.loads(exc.read()).get("error", {})
            except ValueError:
                detail = {}
            raise ApiError(exc.code, detail.get("code", "http_error"), detail.get("message", ""))
        except (error.URLError, OSError, TimeoutError) as exc:
            raise TransportError(str(exc))


def pair(base_url, code, allow_insecure_localhost=False, timeout=30):
    transport = HttpTransport(base_url, "", timeout, allow_insecure_localhost)
    req = request.Request(transport.base_url + "/v1/pair", data=json.dumps({"code": code}).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read())
    except error.HTTPError as exc:
        raise ApiError(exc.code, "pairing_failed", exc.read().decode(errors="replace")[:300])


class Journal:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS jobs (
            task_id TEXT PRIMARY KEY, lease_id TEXT NOT NULL, payload_sha256 TEXT NOT NULL, action TEXT NOT NULL,
            params TEXT NOT NULL, phase TEXT NOT NULL, outcome TEXT, result TEXT, updated REAL NOT NULL)""")

    def put(self, task, phase):
        self.db.execute("INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?,?,NULL,NULL,?)",
                        (task["id"], task["lease_id"], task["payload_sha256"], task["action"],
                         json.dumps(task["params"], ensure_ascii=False), phase, time.time()))

    def phase(self, task_id, phase, outcome=None, result=None):
        self.db.execute("UPDATE jobs SET phase=?, outcome=COALESCE(?, outcome), result=COALESCE(?, result), updated=? WHERE task_id=?",
                        (phase, outcome, None if result is None else json.dumps(result, ensure_ascii=False), time.time(), task_id))

    def get(self, task_id):
        return self.db.execute("SELECT * FROM jobs WHERE task_id=?", (task_id,)).fetchone()

    def pending(self):
        return self.db.execute("SELECT * FROM jobs WHERE phase NOT IN ('reported','abandoned') ORDER BY updated").fetchall()

    def close(self):
        self.db.close()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


class Executor:
    """v1 allow-list only. Paths come from local configuration, never from the server."""

    def __init__(self, output_dir, roots):
        self.output = Path(output_dir).resolve()
        self.roots = {name: Path(path).resolve() for name, path in (roots or {}).items()}

    def expected_bytes(self, action, params):
        if action == "note.create":
            return (params["text"] + "\n").encode("utf-8")
        if action == "document.create":
            return params["text"].encode("utf-8")
        return None

    def target(self, task_id, action, params):
        if action == "note.create":
            return self.output / "notes" / f"{task_id}.md"
        if action == "document.create":
            return self.output / "documents" / f"{task_id}-{params['filename']}"
        return self.output / "clips" / f"{task_id}.mp4"

    def source(self, params):
        root = self.roots.get(params["root"])
        if root is None:
            raise ValueError(f"Carpeta '{params['root']}' no autorizada en esta PC")
        path = (root / c.relative_path(params["path"])).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("El archivo está fuera de la carpeta autorizada")
        return path

    def preflight(self, action, params):
        """Checks with no side effects. Raises ValueError: safe to report failed."""
        c.validate_action(action, params)
        if action == "video.clip":
            source = self.source(params)
            if "source_sha256" in params and pilot.file_digest(source) != params["source_sha256"]:
                raise ValueError("El archivo cambió desde que se aprobó")

    def run(self, task_id, action, params):
        """Returns result dict. ValueError = no effect produced; other exceptions = uncertain."""
        target = self.target(task_id, action, params)
        target.parent.mkdir(parents=True, exist_ok=True)
        if action == "video.clip":
            source = self.source(params)
            source_sha = pilot.file_digest(source)
            if params.get("source_sha256", source_sha) != source_sha:
                raise ValueError("El archivo cambió desde que se aprobó")
            payload = {"action": "clip", "source": str(source), "source_sha256": source_sha,
                       "start": params["start_ms"] / 1000, "duration": params["duration_ms"] / 1000}
            produced = Path(pilot.execute(task_id, payload, target.parent))
            data_sha = pilot.file_digest(produced)
            return {"message": "Recorte creado", "output": {"name": produced.name, "sha256": data_sha,
                                                             "bytes": produced.stat().st_size, "source_sha256": source_sha}}
        data = self.expected_bytes(action, params)
        with target.open("xb") as stream:  # never overwrite: a duplicate run fails loudly
            stream.write(data)
        return {"message": "Archivo creado", "output": {"name": target.name, "sha256": sha256_bytes(data), "bytes": len(data)}}

    def verify(self, task_id, action, params):
        """After a crash: confirm a deterministic output exists with exact bytes."""
        expected = self.expected_bytes(action, params)
        target = self.target(task_id, action, params)
        if expected is not None and target.is_file() and target.read_bytes() == expected:
            return {"message": "Verificado tras reinicio", "output": {"name": target.name, "sha256": sha256_bytes(expected), "bytes": len(expected)}}
        return None


class Agent:
    def __init__(self, transport, device_id, journal, executor, clock=time.time, log=None):
        self.call, self.device_id, self.journal, self.executor, self.clock = transport, device_id, journal, executor, clock
        self.log = log or (lambda message: None)
        self.stopped = None  # set to a reason when the device is revoked

    def run_once(self, max_tasks=1):
        """One sync cycle: report pending work, then claim and execute new tasks."""
        try:
            self.recover()
            for task in self.call("POST", "/v1/agent/claim", {"max_tasks": max_tasks})["tasks"]:
                self.process(task)
        except ApiError as exc:
            if exc.status == 401:
                self.stopped = "Dispositivo revocado o credencial inválida; volver a vincular"
            raise
        return self.stopped

    def process(self, task):
        self.journal.put(task, "claimed")
        problem = self.local_check(task)
        if problem:
            self.log(f"{task['id']}: rechazada localmente: {problem}")
            self.journal.phase(task["id"], "done_local", c.FAILED, {"message": problem})
            return self.report(task["id"])
        self.journal.phase(task["id"], "start_sent")
        try:
            self.call("POST", f"/v1/agent/tasks/{task['id']}/start", {"lease_id": task["lease_id"], "payload_sha256": task["payload_sha256"]})
        except ApiError as exc:
            # Server refused: nothing was executed. Forget the job; the server state is authoritative.
            self.log(f"{task['id']}: start rechazado: {exc.code}")
            self.journal.phase(task["id"], "abandoned")
            return
        self.journal.phase(task["id"], "running")
        outcome, result = self.execute(task["id"], task["action"], task["params"])
        self.journal.phase(task["id"], "done_local", outcome, result)
        self.report(task["id"])

    def local_check(self, task):
        """Independent re-check of what the server sent: exact content, target and approval validity."""
        try:
            digest = c.task_digest(task["action"], task["params"], task["target_device_id"])
        except c.ContractError as exc:
            return str(exc)
        approval = task.get("approval") or {}
        if not digest == task["payload_sha256"] == approval.get("payload_sha256"):
            return "La huella no coincide con lo aprobado"
        if task["target_device_id"] not in (None, self.device_id):
            return "La tarea es para otro dispositivo"
        if not approval.get("expires_at") or approval["expires_at"] <= self.clock():
            return "Aprobación vencida"
        try:
            self.executor.preflight(task["action"], task["params"])
        except (ValueError, OSError) as exc:
            return str(exc)
        return None

    def execute(self, task_id, action, params):
        try:
            return c.SUCCEEDED, self.executor.run(task_id, action, params)
        except (ValueError, FileNotFoundError) as exc:
            return c.FAILED, {"message": str(exc)[:2000]}
        except (RuntimeError, subprocess.TimeoutExpired, OSError, Exception) as exc:
            return c.UNKNOWN, {"message": f"Resultado incierto: {type(exc).__name__}: {str(exc)[:1500]}"}

    def report(self, task_id):
        job = self.journal.get(task_id)
        try:
            self.call("POST", f"/v1/agent/tasks/{task_id}/complete",
                      {"lease_id": job["lease_id"], "outcome": job["outcome"], "result": json.loads(job["result"] or "{}")})
        except ApiError as exc:
            if exc.status in (401, 429) or exc.status >= 500:
                raise
            self.log(f"{task_id}: informe rechazado: {exc.code}")
            self.journal.phase(task_id, "abandoned")
            return
        self.journal.phase(task_id, "reported")

    def recover(self):
        """Re-send results and settle interrupted work without repeating effects."""
        for job in self.journal.pending():
            params = json.loads(job["params"])
            if job["phase"] == "done_local":
                self.report(job["task_id"])
            elif job["phase"] in ("claimed", "start_sent"):
                # Not executed yet. The server decides whether start went through.
                try:
                    task = self.call("GET", f"/v1/agent/tasks/{job['task_id']}")["task"]
                except ApiError as exc:
                    if exc.status == 401:
                        raise
                    task = {"state": None}
                state = task["state"]
                if state == c.RUNNING and task["lease_id"] == job["lease_id"] and job["phase"] == "start_sent":
                    # Start was accepted but its response was lost: still authorized, still no effect.
                    self.journal.phase(job["task_id"], "running")
                    outcome, result = self.execute(job["task_id"], job["action"], params)
                    self.journal.phase(job["task_id"], "done_local", outcome, result)
                    self.report(job["task_id"])
                elif state in (c.RUNNING, c.UNKNOWN):
                    self.journal.phase(job["task_id"], "done_local", c.FAILED, {"message": "No ejecutada: el agente se reinició antes de empezar"})
                    self.report(job["task_id"])
                else:
                    self.journal.phase(job["task_id"], "abandoned")
            elif job["phase"] == "running":
                verified = self.executor.verify(job["task_id"], job["action"], params)
                outcome, result = (c.SUCCEEDED, verified) if verified else (
                    c.UNKNOWN, {"message": "Interrumpida durante la ejecución; revisar la PC antes de reintentar"})
                self.journal.phase(job["task_id"], "done_local", outcome, result)
                self.report(job["task_id"])


# --- local secret storage ----------------------------------------------------------

def protect(data: bytes) -> bytes:
    """DPAPI (current Windows user) when available; otherwise returned as-is for a 0600 file."""
    if os.name != "nt":
        return data
    return _dpapi(data, protect=True)


def unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        return data
    return _dpapi(data, protect=False)


def _dpapi(data, protect):
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buffer = ctypes.create_string_buffer(data, len(data))
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    output = Blob()
    crypt = ctypes.windll.crypt32
    fn = crypt.CryptProtectData if protect else crypt.CryptUnprotectData
    if not fn(ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(output)):  # CRYPTPROTECT_UI_FORBIDDEN
        raise OSError("DPAPI no pudo proteger/leer la credencial")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def save_secret(path, token):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = protect(token.encode())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def load_secret(path):
    return unprotect(Path(path).read_bytes()).decode()
