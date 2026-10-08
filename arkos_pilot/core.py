import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import uuid


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Queue:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.output = self.root / "outputs"
        self.output.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / "queue.sqlite3", timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY, payload TEXT NOT NULL, fingerprint TEXT NOT NULL,
            state TEXT NOT NULL, approval_until REAL, approved_fingerprint TEXT,
            created REAL NOT NULL, updated REAL NOT NULL, result TEXT)""")
        self.db.commit()

    def close(self):
        self.db.close()

    def add(self, payload):
        validate(payload)
        task_id = uuid.uuid4().hex
        now = time.time()
        self.db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?)", (
            task_id, json.dumps(payload, ensure_ascii=False), digest(payload), "awaiting_approval",
            None, None, now, now, None))
        self.db.commit()
        return self.get(task_id)

    def get(self, task_id):
        row = self.db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise ValueError("Tarea inexistente")
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result

    def list(self):
        return [self.get(row[0]) for row in self.db.execute("SELECT id FROM tasks ORDER BY created")]

    def approve(self, task_id, fingerprint, hours=24):
        if not 0 < hours <= 24:
            raise ValueError("La aprobación dura como máximo 24 horas")
        now = time.time()
        changed = self.db.execute("""UPDATE tasks SET state='queued', approved_fingerprint=?,
            approval_until=?, updated=? WHERE id=? AND fingerprint=? AND state IN ('awaiting_approval','blocked')""",
            (fingerprint, now + hours * 3600, now, task_id, fingerprint)).rowcount
        self.db.commit()
        if changed != 1:
            raise ValueError("No se aprobó: revisa ID, huella y estado de la tarea")
        return self.get(task_id)

    def cancel(self, task_id):
        changed = self.db.execute("UPDATE tasks SET state='cancelled', updated=? WHERE id=? AND state IN ('awaiting_approval','queued','blocked')", (time.time(), task_id)).rowcount
        self.db.commit()
        if not changed:
            raise ValueError("La tarea no puede cancelarse en ese estado")
        return self.get(task_id)

    def recover(self):
        """Only on explicit operator request after ensuring no other worker is running."""
        self.db.execute("UPDATE tasks SET state='blocked', result='Ejecución interrumpida: revisar salida antes de aprobar otra vez', updated=? WHERE state='running'", (time.time(),))
        self.db.commit()

    def run_next(self, task_id=None):
        self.db.execute("BEGIN IMMEDIATE")
        if task_id is None:
            row = self.db.execute("SELECT id FROM tasks WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
        else:
            row = self.db.execute("SELECT id FROM tasks WHERE state='queued' AND id=?", (task_id,)).fetchone()
        if not row:
            self.db.commit()
            return None
        task = self.get(row[0])
        valid = (task["approval_until"] and task["approval_until"] > time.time()
                 and task["approved_fingerprint"] == task["fingerprint"] == digest(task["payload"]))
        state = "running" if valid else "blocked"
        self.db.execute("UPDATE tasks SET state=?, updated=? WHERE id=?", (state, time.time(), task["id"]))
        self.db.commit()
        if not valid:
            return self.get(task["id"])
        try:
            result = execute(task["id"], task["payload"], self.output)
            state = "completed"
        except Exception as exc:
            result, state = str(exc), "blocked"
        self.db.execute("UPDATE tasks SET state=?, result=?, updated=? WHERE id=? AND state='running'", (state, result, time.time(), task["id"]))
        self.db.commit()
        return self.get(task["id"])


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("Acción inválida")
    action = payload.get("action")
    if action == "note":
        if set(payload) != {"action", "text"} or not isinstance(payload["text"], str) or not payload["text"].strip() or len(payload["text"]) > 100000:
            raise ValueError("Nota vacía o demasiado extensa")
    elif action == "clip":
        if set(payload) != {"action", "source", "source_sha256", "start", "duration"}:
            raise ValueError("Recorte incompleto")
        if not isinstance(payload["source"], str) or not Path(payload["source"]).is_absolute():
            raise ValueError("El archivo debe tener ruta absoluta")
        if not isinstance(payload["source_sha256"], str) or len(payload["source_sha256"]) != 64:
            raise ValueError("Huella del archivo inválida")
        for key in ("start", "duration"):
            if type(payload[key]) not in (int, float) or not 0 <= payload[key] <= 86400:
                raise ValueError("Tiempos inválidos")
        if not payload["duration"]:
            raise ValueError("Duración debe ser positiva")
    else:
        raise ValueError("Acción no soportada; no se ejecutan comandos arbitrarios")


def file_digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clip_payload(source, start, duration):
    path = Path(source).resolve(strict=True)
    payload = {"action": "clip", "source": str(path), "source_sha256": file_digest(path), "start": start, "duration": duration}
    validate(payload)
    return payload


def execute(task_id, payload, output):
    validate(payload)
    if payload["action"] == "note":
        target = output / (task_id + ".md")
        # Exclusive creation prevents a recovered task from overwriting prior output.
        with target.open("x", encoding="utf-8") as stream:
            stream.write(payload["text"] + "\n")
        return str(target)
    command = shutil.which("ffmpeg")
    if not command:
        raise ValueError("FFmpeg no está instalado o no está en PATH; instala y verifica antes de volver a aprobar")
    if file_digest(payload["source"]) != payload["source_sha256"]:
        raise ValueError("El archivo cambió desde la propuesta; crea una tarea nueva")
    target = output / (task_id + ".mp4")
    args = [command, "-nostdin", "-hide_banner", "-loglevel", "error", "-n", "-ss", str(payload["start"]),
            "-i", payload["source"], "-t", str(payload["duration"]), "-map", "0:v:0?", "-map", "0:a:0?",
            "-c:v", "mpeg4", "-c:a", "aac", str(target)]
    result = subprocess.run(args, shell=False, capture_output=True, timeout=600)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[-2000:])
    return str(target)
