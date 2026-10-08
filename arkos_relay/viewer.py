"""Read-only mirror of the relay queue for the PC screen.

Uses its own viewer credential (akr_), never the device token: it can list tasks
but cannot approve, claim, start or complete them. Nothing here touches the
agent journal or arkos_pilot.Queue. The output is a size-bounded JSON snapshot,
written atomically, with no tokens, lease ids or idempotency keys.
"""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

from . import contract as c
from .agent import ApiError, TransportError

SCHEMA = "arkos.relay.snapshot"
SCHEMA_VERSION = 1
SNAPSHOT_NAME = "relay-snapshot.json"
MAX_TASKS = 500
MAX_BYTES = 1024 * 1024
PREVIEW_CHARS = 280
MESSAGE_CHARS = 500
STALE_AFTER_SECONDS = 120
PAGE_SIZE = 200
MAX_PAGES = 50
FULL_RESYNC_SECONDS = 600
OUTPUT_DIRS = {"note.create": "notes", "document.create": "documents", "video.clip": "clips"}
ACTIVE = (c.AWAITING_APPROVAL, c.APPROVED, c.CLAIMED, c.RUNNING, c.UNKNOWN)


class ViewerSync:
    def __init__(self, transport, state_dir, device_id, outputs_dir=None, clock=time.time,
                 stale_after=STALE_AFTER_SECONDS, page_size=PAGE_SIZE):
        self.call, self.device_id, self.clock = transport, device_id, clock
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.outputs = Path(outputs_dir) if outputs_dir else None
        self.stale_after, self.page_size = stale_after, page_size
        self.snapshot_path = self.state_dir / SNAPSHOT_NAME
        self.db = sqlite3.connect(str(self.state_dir / "viewer.sqlite3"), timeout=10, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, version INTEGER NOT NULL, data TEXT NOT NULL)")

    def close(self):
        self.db.close()

    def _get(self, key, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _set(self, **values):
        for key, value in values.items():
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value)))

    def sync(self):
        """Fetch changes since the cursor, then rewrite the snapshot. Never raises on network errors.

        The first sync of each process and one every FULL_RESYNC_SECONDS re-reads the whole
        visible queue and replaces the mirror atomically. That covers a relay restored from
        a backup, whose version counter can grow back past the local cursor.
        """
        now = self.clock()
        self._set(last_attempt_at=now)
        try:
            cursor = self._get("cursor", 0)
            full = self._full_due(now)
            tasks, head = self._fetch(0 if full else cursor)
            if not full and head < cursor:
                full = True
                tasks, head = self._fetch(0)
            self.db.execute("BEGIN IMMEDIATE")
            try:
                if full:
                    self.db.execute("DELETE FROM tasks")
                    cursor = 0
                for task in tasks:
                    self.db.execute("INSERT OR REPLACE INTO tasks VALUES (?,?,?)", (task["id"], task["version"], json.dumps(task)))
                    cursor = max(cursor, task["version"])
                self._set(cursor=cursor, last_success_at=self.clock(), last_error=None)
                if full:
                    self._set(last_full_at=now)
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            self.full_done = True
        except TransportError:
            self._set(last_error="offline")
        except ApiError as exc:
            self._set(last_error="unauthorized" if exc.status == 401 else f"http_{exc.status}")
        return self.write_snapshot()

    def _full_due(self, now):
        last_full = self._get("last_full_at")
        return not getattr(self, "full_done", False) or last_full is None or now - last_full > FULL_RESYNC_SECONDS

    def _fetch(self, after):
        """All pages after a version, kept in memory until complete (a cut leaves the mirror untouched)."""
        tasks, head = [], 0
        for _ in range(MAX_PAGES):
            page = self.call("GET", f"/v1/viewer/tasks?after_version={after}&limit={self.page_size}")
            tasks.extend(page["tasks"])
            head = page["head_version"]
            if not page["has_more"] or not page["tasks"]:
                return tasks, head
            after = page["tasks"][-1]["version"]
        raise TransportError("Demasiadas páginas; se reintentará")

    def status(self, now=None):
        now = self.clock() if now is None else now
        last_success, error = self._get("last_success_at"), self._get("last_error")
        if error == "unauthorized":
            return "unauthorized"
        if last_success is None:
            return "never_synced"
        if error:
            return "offline"
        return "stale" if now - last_success > self.stale_after else "fresh"

    def build_snapshot(self):
        now = self.clock()
        tasks = [json.loads(row[0]) for row in self.db.execute("SELECT data FROM tasks")]
        # Active work first, then most recently updated; the screen must never lose a pending decision.
        tasks.sort(key=lambda t: (t["state"] not in ACTIVE, -t["updated_at"]))
        cards = [self.card(t) for t in tasks[:MAX_TASKS]]
        snapshot = {
            "schema": SCHEMA, "schema_version": SCHEMA_VERSION, "source": "relay",
            "generated_at": now, "device_id": self.device_id,
            "sync": {"status": self.status(now), "last_success_at": self._get("last_success_at"),
                     "last_attempt_at": self._get("last_attempt_at"), "last_error": self._get("last_error"),
                     "stale_after_seconds": self.stale_after, "cursor": self._get("cursor", 0)},
            "limits": {"max_tasks": MAX_TASKS, "max_bytes": MAX_BYTES, "preview_chars": PREVIEW_CHARS},
            "truncated": len(tasks) > MAX_TASKS, "task_count": len(cards), "tasks": cards,
        }
        data = _encode(snapshot)
        while len(data) > MAX_BYTES and snapshot["tasks"]:
            # Drop from the end: oldest terminal tasks go first because of the sort above.
            snapshot["tasks"] = snapshot["tasks"][:-max(1, len(snapshot["tasks"]) // 10)]
            snapshot["truncated"], snapshot["task_count"] = True, len(snapshot["tasks"])
            data = _encode(snapshot)
        return snapshot, data

    def card(self, task):
        params = task["params"]
        summary = {}
        if task["action"] in ("note.create", "document.create"):
            summary["preview"] = _cut(params["text"], PREVIEW_CHARS)
            summary["title"] = params.get("filename") or _cut(params["text"].strip().splitlines()[0], 80)
        else:
            summary.update(title=params["path"].split("/")[-1], root=params["root"], path=params["path"],
                           start_ms=params["start_ms"], duration_ms=params["duration_ms"])
        result = task.get("result")
        if result:
            result = dict(result)
            if "message" in result:
                result["message"] = _cut(result["message"], MESSAGE_CHARS)
        return {
            "origin": "relay", "remote_id": task["id"], "version": task["version"], "action": task["action"],
            "state": task["state"], "state_reason": task["state_reason"],
            "target_device_id": task["target_device_id"],
            "for_this_device": task["target_device_id"] in (None, self.device_id),
            "created_at": task["created_at"], "updated_at": task["updated_at"],
            "approval_expires_at": task.get("approval_expires_at"), "attempts": task["attempts"],
            "retry_of": task["retry_of"], "payload_sha256": task["payload_sha256"],
            "summary": summary, "result": result, "artifact": self.artifact(task),
        }

    def artifact(self, task):
        output = (task.get("result") or {}).get("output")
        if task["state"] != c.SUCCEEDED or not output:
            return {"status": "none"}
        relative = f"{OUTPUT_DIRS[task['action']]}/{output['name']}"
        info = {"relative_path": relative, "sha256": output.get("sha256"), "bytes": output.get("bytes")}
        if not self.outputs:
            return {"status": "unknown", **info}
        path = self.outputs / relative
        if not path.is_file():
            return {"status": "missing", **info}  # e.g. executed on another PC, or deleted
        if output.get("bytes") is not None and path.stat().st_size != output["bytes"]:
            return {"status": "mismatch", **info}
        return {"status": "available", **info}  # reader must still verify sha256 before opening

    def write_snapshot(self):
        snapshot, data = self.build_snapshot()
        atomic_write(self.snapshot_path, data)
        return snapshot


def _cut(text, limit):
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _encode(snapshot):
    return json.dumps(snapshot, ensure_ascii=False, indent=1).encode("utf-8")


def atomic_write(path, data, attempts=5):
    """Write to a temp file in the same folder, fsync, then rename over the old snapshot.

    Readers see either the previous or the new file, never a partial one. On Windows a
    reader holding the file open blocks the rename, so it is retried briefly; if it still
    fails the previous snapshot stays in place.
    """
    path = Path(path)
    fd, temp = tempfile.mkstemp(prefix=".snapshot-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(attempts):
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                time.sleep(0.05)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_snapshot(path, now=None, stale_after=None):
    """Reference reader: validates schema/size and recomputes freshness with the reader's clock."""
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Snapshot demasiado grande")
    snapshot = json.loads(path.read_bytes())
    if snapshot.get("schema") != SCHEMA or snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Versión de snapshot no soportada")
    sync = snapshot["sync"]
    now = time.time() if now is None else now
    limit = stale_after or sync["stale_after_seconds"]
    if sync["status"] == "fresh" and (sync["last_success_at"] is None or now - sync["last_success_at"] > limit):
        sync["status"] = "stale"
    return snapshot
