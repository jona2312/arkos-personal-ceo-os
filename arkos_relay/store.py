"""Persistent relay queue. Every user-facing call is scoped by the authenticated user_id."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import uuid

from . import contract as c

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
INSERT OR IGNORE INTO meta VALUES ('version', 0);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, display_name TEXT NOT NULL, created_at REAL NOT NULL, disabled_at REAL);
CREATE TABLE IF NOT EXISTS user_tokens (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), label TEXT,
  created_at REAL NOT NULL, revoked_at REAL);
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE, created_at REAL NOT NULL, last_seen_at REAL, revoked_at REAL);
CREATE TABLE IF NOT EXISTS pairing_codes (
  code_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), device_name TEXT NOT NULL,
  created_at REAL NOT NULL, expires_at REAL NOT NULL, used_at REAL);
CREATE TABLE IF NOT EXISTS channel_bindings (
  channel TEXT NOT NULL, address TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id),
  created_at REAL NOT NULL, PRIMARY KEY (channel, address));
CREATE TABLE IF NOT EXISTS channel_messages (
  channel TEXT NOT NULL, message_id TEXT NOT NULL, user_id TEXT, received_at REAL NOT NULL,
  PRIMARY KEY (channel, message_id));
CREATE TABLE IF NOT EXISTS channel_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT NOT NULL, address TEXT NOT NULL,
  user_id TEXT NOT NULL, text TEXT NOT NULL, created_at REAL NOT NULL, sent_at REAL);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), target_device_id TEXT,
  client_request_id TEXT NOT NULL, channel TEXT NOT NULL, action TEXT NOT NULL, params TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL, state TEXT NOT NULL, state_reason TEXT, retry_of TEXT,
  lease_id TEXT, lease_device_id TEXT, lease_expires_at REAL, attempts INTEGER NOT NULL DEFAULT 0,
  result TEXT, result_sha256 TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL,
  version INTEGER NOT NULL, UNIQUE (user_id, client_request_id));
CREATE INDEX IF NOT EXISTS idx_tasks_claim ON tasks(user_id, state, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_version ON tasks(user_id, version);
CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), user_id TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL, channel TEXT NOT NULL, created_at REAL NOT NULL,
  expires_at REAL NOT NULL, consumed_at REAL, revoked_at REAL);
CREATE TABLE IF NOT EXISTS task_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, user_id TEXT NOT NULL, at REAL NOT NULL,
  actor TEXT NOT NULL, from_state TEXT, to_state TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS viewer_codes (
  code_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), device_id TEXT NOT NULL REFERENCES devices(id),
  created_at REAL NOT NULL, expires_at REAL NOT NULL, used_at REAL);
CREATE TABLE IF NOT EXISTS viewer_tokens (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), device_id TEXT NOT NULL REFERENCES devices(id),
  created_at REAL NOT NULL, revoked_at REAL);
"""

PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I


class RelayError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def not_found():
    # Same answer for "missing" and "belongs to someone else": no existence oracle.
    return RelayError(404, "not_found", "Recurso inexistente")


def conflict(code, message):
    return RelayError(409, code, message)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def new_token(prefix):
    return f"{prefix}_{secrets.token_urlsafe(32)}"


class Store:
    def __init__(self, path, clock=time.time, claim_lease_seconds=120, run_lease_seconds=900):
        self.path = Path(path)
        self.clock = clock
        self.claim_lease_seconds = claim_lease_seconds
        self.run_lease_seconds = run_lease_seconds
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    @contextmanager
    def tx(self):
        """Serialized write transaction; BEGIN IMMEDIATE also protects across processes."""
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self._sweep()
                yield self.db
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def _next_version(self):
        self.db.execute("UPDATE meta SET value = value + 1 WHERE key='version'")
        return self.db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0]

    def _transition(self, task, to_state, actor, reason=None, **fields):
        now = self.clock()
        fields.update(state=to_state, state_reason=reason, updated_at=now, version=self._next_version())
        assignments = ", ".join(f"{key}=?" for key in fields)
        self.db.execute(f"UPDATE tasks SET {assignments} WHERE id=?", (*fields.values(), task["id"]))
        self._event(task["id"], task["user_id"], actor, task["state"], to_state, reason)

    def _event(self, task_id, user_id, actor, from_state, to_state, detail=None):
        self.db.execute("INSERT INTO task_events (task_id, user_id, at, actor, from_state, to_state, detail) VALUES (?,?,?,?,?,?,?)",
                        (task_id, user_id, self.clock(), actor, from_state, to_state, detail))

    def _sweep(self):
        """Expire leases and approvals. Never re-runs anything that may have started."""
        now = self.clock()
        for task in self.db.execute("SELECT * FROM tasks WHERE state=? AND lease_expires_at < ?", (c.CLAIMED, now)).fetchall():
            # Claimed but never started: no effect happened, safe to offer again if still approved.
            target = c.APPROVED if self._valid_approval(task, now) else c.AWAITING_APPROVAL
            reason = "lease_expired_before_start" if target == c.APPROVED else "approval_expired"
            self._transition(task, target, "system", reason, lease_id=None, lease_device_id=None, lease_expires_at=None)
        for task in self.db.execute("SELECT * FROM tasks WHERE state=? AND lease_expires_at < ?", (c.RUNNING, now)).fetchall():
            # Started and silent: the effect may or may not exist. Keep the lease id so a late report is accepted.
            self._transition(task, c.UNKNOWN, "system", "lease_expired_during_execution")
        for task in self.db.execute("SELECT * FROM tasks WHERE state=?", (c.APPROVED,)).fetchall():
            if not self._valid_approval(task, now):
                self._transition(task, c.AWAITING_APPROVAL, "system", "approval_expired")

    def _valid_approval(self, task, now):
        return self.db.execute(
            "SELECT * FROM approvals WHERE task_id=? AND payload_sha256=? AND consumed_at IS NULL AND revoked_at IS NULL AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
            (task["id"], task["payload_sha256"], now)).fetchone()

    # --- users, tokens and channels -------------------------------------------------

    def create_user(self, display_name):
        user_id = "usr_" + uuid.uuid4().hex
        with self.tx() as db:
            db.execute("INSERT INTO users VALUES (?,?,?,NULL)", (user_id, display_name, self.clock()))
        return user_id

    def issue_user_token(self, user_id, label="phone"):
        token = new_token("aku")
        with self.tx() as db:
            if not db.execute("SELECT 1 FROM users WHERE id=? AND disabled_at IS NULL", (user_id,)).fetchone():
                raise not_found()
            db.execute("INSERT INTO user_tokens VALUES (?,?,?,?,NULL)", (token_hash(token), user_id, label, self.clock()))
        return token

    def revoke_user_token(self, token):
        with self.tx() as db:
            db.execute("UPDATE user_tokens SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL", (self.clock(), token_hash(token)))

    def auth_user(self, token):
        with self.lock:
            row = self.db.execute("""SELECT u.id FROM user_tokens t JOIN users u ON u.id=t.user_id
                WHERE t.token_hash=? AND t.revoked_at IS NULL AND u.disabled_at IS NULL""", (token_hash(token),)).fetchone()
        return row["id"] if row else None

    def auth_device(self, token):
        with self.lock:
            row = self.db.execute("""SELECT d.id, d.user_id FROM devices d JOIN users u ON u.id=d.user_id
                WHERE d.token_hash=? AND d.revoked_at IS NULL AND u.disabled_at IS NULL""", (token_hash(token),)).fetchone()
            if row:
                self.db.execute("UPDATE devices SET last_seen_at=? WHERE id=?", (self.clock(), row["id"]))
        return (row["user_id"], row["id"]) if row else None

    def auth_viewer(self, token):
        """Read-only credential: one user, one device, no approve/claim/execute routes."""
        with self.lock:
            row = self.db.execute("""SELECT v.user_id, v.device_id FROM viewer_tokens v
                JOIN devices d ON d.id=v.device_id JOIN users u ON u.id=v.user_id
                WHERE v.token_hash=? AND v.revoked_at IS NULL AND d.revoked_at IS NULL AND u.disabled_at IS NULL""",
                (token_hash(token),)).fetchone()
        return (row["user_id"], row["device_id"]) if row else None

    def bind_channel(self, user_id, channel, address):
        with self.tx() as db:
            db.execute("INSERT OR REPLACE INTO channel_bindings VALUES (?,?,?,?)", (channel, address, user_id, self.clock()))

    def user_for_channel(self, channel, address):
        with self.lock:
            row = self.db.execute("""SELECT b.user_id FROM channel_bindings b JOIN users u ON u.id=b.user_id
                WHERE b.channel=? AND b.address=? AND u.disabled_at IS NULL""", (channel, address)).fetchone()
        return row["user_id"] if row else None

    def first_seen(self, channel, message_id, user_id):
        """True the first time a channel message id is seen (webhook retries are dropped)."""
        with self.tx() as db:
            try:
                db.execute("INSERT INTO channel_messages VALUES (?,?,?,?)", (channel, message_id, user_id, self.clock()))
                return True
            except sqlite3.IntegrityError:
                return False

    def enqueue_reply(self, channel, address, user_id, text):
        with self.tx() as db:
            db.execute("INSERT INTO channel_outbox (channel, address, user_id, text, created_at) VALUES (?,?,?,?,?)",
                       (channel, address, user_id, text, self.clock()))

    def outbox(self, channel):
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM channel_outbox WHERE channel=? AND sent_at IS NULL ORDER BY id", (channel,))]

    # --- devices ----------------------------------------------------------------------

    def create_pairing_code(self, user_id, device_name, ttl_seconds=600):
        if not isinstance(device_name, str) or not 0 < len(device_name.strip()) <= 80:
            raise RelayError(400, "invalid_request", "Nombre de dispositivo inválido")
        code = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(12))
        now = self.clock()
        with self.tx() as db:
            db.execute("INSERT INTO pairing_codes VALUES (?,?,?,?,?,NULL)", (token_hash(code), user_id, device_name.strip(), now, now + ttl_seconds))
        return {"code": f"{code[:4]}-{code[4:8]}-{code[8:]}", "expires_at": now + ttl_seconds}

    def pair_device(self, code):
        normalized = "".join(ch for ch in str(code).upper() if ch.isalnum())
        now = self.clock()
        with self.tx() as db:
            row = db.execute("SELECT * FROM pairing_codes WHERE code_hash=?", (token_hash(normalized),)).fetchone()
            if not row or row["used_at"] is not None or row["expires_at"] <= now:
                raise RelayError(401, "invalid_pairing_code", "Código de vinculación inválido, usado o vencido")
            db.execute("UPDATE pairing_codes SET used_at=? WHERE code_hash=?", (now, row["code_hash"]))
            device_id = "dev_" + uuid.uuid4().hex
            token = new_token("akd")
            db.execute("INSERT INTO devices VALUES (?,?,?,?,?,NULL,NULL)", (device_id, row["user_id"], row["device_name"], token_hash(token), now))
        return {"device_id": device_id, "device_token": token, "user_id": row["user_id"], "name": row["device_name"]}

    def list_devices(self, user_id):
        with self.lock:
            rows = self.db.execute("SELECT id, name, created_at, last_seen_at, revoked_at FROM devices WHERE user_id=? ORDER BY created_at", (user_id,))
            return [dict(r) for r in rows]

    def revoke_device(self, user_id, device_id):
        with self.tx() as db:
            if not db.execute("SELECT 1 FROM devices WHERE id=? AND user_id=?", (device_id, user_id)).fetchone():
                raise not_found()
            db.execute("UPDATE devices SET revoked_at=COALESCE(revoked_at, ?) WHERE id=?", (self.clock(), device_id))
            db.execute("UPDATE viewer_tokens SET revoked_at=COALESCE(revoked_at, ?) WHERE device_id=?", (self.clock(), device_id))
            for task in db.execute("SELECT * FROM tasks WHERE lease_device_id=? AND state IN (?,?)", (device_id, c.CLAIMED, c.RUNNING)).fetchall():
                if task["state"] == c.CLAIMED:
                    target = c.APPROVED if self._valid_approval(task, self.clock()) else c.AWAITING_APPROVAL
                    self._transition(task, target, f"user:{user_id}", "device_revoked_before_start", lease_id=None, lease_device_id=None, lease_expires_at=None)
                else:
                    self._transition(task, c.UNKNOWN, f"user:{user_id}", "device_revoked_during_execution")
        return {"device_id": device_id, "revoked": True}

    # --- read-only viewer (PC screen) ------------------------------------------------

    def create_viewer_code(self, user_id, device_id, ttl_seconds=600):
        """Issued by the user, never by the device itself: reading the whole queue needs explicit consent."""
        code = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(12))
        now = self.clock()
        with self.tx() as db:
            if not db.execute("SELECT 1 FROM devices WHERE id=? AND user_id=? AND revoked_at IS NULL", (device_id, user_id)).fetchone():
                raise not_found()
            db.execute("INSERT INTO viewer_codes VALUES (?,?,?,?,?,NULL)", (token_hash(code), user_id, device_id, now, now + ttl_seconds))
        return {"code": f"{code[:4]}-{code[4:8]}-{code[8:]}", "expires_at": now + ttl_seconds, "device_id": device_id}

    def pair_viewer(self, code):
        normalized = "".join(ch for ch in str(code).upper() if ch.isalnum())
        now = self.clock()
        with self.tx() as db:
            row = db.execute("""SELECT c.* FROM viewer_codes c JOIN devices d ON d.id=c.device_id
                WHERE c.code_hash=? AND d.revoked_at IS NULL""", (token_hash(normalized),)).fetchone()
            if not row or row["used_at"] is not None or row["expires_at"] <= now:
                raise RelayError(401, "invalid_viewer_code", "Código de lectura inválido, usado o vencido")
            db.execute("UPDATE viewer_codes SET used_at=? WHERE code_hash=?", (now, row["code_hash"]))
            token = new_token("akr")
            db.execute("INSERT INTO viewer_tokens VALUES (?,?,?,?,NULL)", (token_hash(token), row["user_id"], row["device_id"], now))
        return {"device_id": row["device_id"], "viewer_token": token}

    def revoke_viewer_tokens(self, user_id, device_id):
        with self.tx() as db:
            if not db.execute("SELECT 1 FROM devices WHERE id=? AND user_id=?", (device_id, user_id)).fetchone():
                raise not_found()
            count = db.execute("UPDATE viewer_tokens SET revoked_at=? WHERE device_id=? AND user_id=? AND revoked_at IS NULL",
                               (self.clock(), device_id, user_id)).rowcount
        return {"device_id": device_id, "revoked_viewer_tokens": count}

    def viewer_tasks(self, user_id, device_id, after_version=0, limit=200):
        """Tasks for this device or for any device of the user. Pure read apart from time-based expiry."""
        limit = max(1, min(int(limit), 500))
        with self.tx() as db:
            rows = db.execute("""SELECT * FROM tasks WHERE user_id=? AND (target_device_id IS NULL OR target_device_id=?)
                AND version>? ORDER BY version LIMIT ?""", (user_id, device_id, int(after_version), limit + 1)).fetchall()
            head = db.execute("SELECT value FROM meta WHERE key='version'").fetchone()[0]
            tasks = []
            for row in rows[:limit]:
                approval = db.execute("""SELECT expires_at FROM approvals WHERE task_id=? AND revoked_at IS NULL
                    ORDER BY created_at DESC LIMIT 1""", (row["id"],)).fetchone()
                task = self.public_task(row)
                for private in ("lease_id", "lease_expires_at", "client_request_id"):
                    task.pop(private)
                task["approval_expires_at"] = approval["expires_at"] if approval and row["state"] in (c.APPROVED, c.CLAIMED) else None
                tasks.append(task)
        return {"tasks": tasks, "has_more": len(rows) > limit, "head_version": head}

    def _active_devices(self, user_id):
        return [r["id"] for r in self.db.execute("SELECT id FROM devices WHERE user_id=? AND revoked_at IS NULL", (user_id,))]

    # --- tasks: user side -------------------------------------------------------------

    def _task(self, user_id, task_id):
        row = self.db.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (task_id, user_id)).fetchone()
        if not row:
            raise not_found()
        return row

    def create_task(self, user_id, client_request_id, action, params, target_device_id=None, channel="api", retry_of=None):
        c.validate_id(client_request_id, "client_request_id")
        c.validate_action(action, params)
        with self.tx() as db:
            existing = db.execute("SELECT * FROM tasks WHERE user_id=? AND client_request_id=?", (user_id, client_request_id)).fetchone()
            if existing:
                same = existing["action"] == action and json.loads(existing["params"]) == params and (
                    target_device_id is None or target_device_id == existing["target_device_id"])
                if not same:
                    raise conflict("idempotency_conflict", "client_request_id ya usado con otro contenido")
                return self.public_task(existing), False
            active = self._active_devices(user_id)
            if target_device_id is None:
                if len(active) > 1:
                    raise RelayError(400, "target_required", "Hay varios dispositivos: indicar target_device_id")
                target_device_id = active[0] if active else None
            elif target_device_id not in active:
                raise not_found()
            task_id = "tsk_" + uuid.uuid4().hex
            now = self.clock()
            digest = c.task_digest(action, params, target_device_id)
            db.execute("""INSERT INTO tasks (id, user_id, target_device_id, client_request_id, channel, action, params,
                payload_sha256, state, retry_of, created_at, updated_at, version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (task_id, user_id, target_device_id, client_request_id, channel, action,
                 json.dumps(params, ensure_ascii=False), digest, c.AWAITING_APPROVAL, retry_of, now, now, self._next_version()))
            self._event(task_id, user_id, f"{channel}:{user_id}", None, c.AWAITING_APPROVAL, retry_of and f"retry_of:{retry_of}")
            return self.public_task(self._task(user_id, task_id)), True

    def get_task(self, user_id, task_id, with_events=False):
        with self.tx():
            task = self.public_task(self._task(user_id, task_id))
            if with_events:
                task["events"] = [dict(r) for r in self.db.execute(
                    "SELECT at, actor, from_state, to_state, detail FROM task_events WHERE task_id=? ORDER BY id", (task_id,))]
            return task

    def list_tasks(self, user_id, after_version=0, limit=100):
        with self.tx() as db:
            rows = db.execute("SELECT * FROM tasks WHERE user_id=? AND version>? ORDER BY version LIMIT ?",
                              (user_id, int(after_version), max(1, min(int(limit), 500)))).fetchall()
            return [self.public_task(r) for r in rows]

    def find_by_prefix(self, user_id, prefix):
        with self.tx() as db:
            rows = db.execute("SELECT * FROM tasks WHERE user_id=? AND id LIKE ? LIMIT 2", (user_id, "tsk_" + prefix + "%")).fetchall()
            if len(rows) != 1:
                raise not_found()
            return self.public_task(rows[0])

    def approve(self, user_id, task_id, payload_sha256, ttl_seconds=c.MAX_APPROVAL_SECONDS, channel="api"):
        if type(ttl_seconds) is not int or not 0 < ttl_seconds <= c.MAX_APPROVAL_SECONDS:
            raise RelayError(400, "invalid_ttl", "La aprobación dura entre 1 s y 24 h")
        with self.tx() as db:
            task = self._task(user_id, task_id)
            if task["state"] != c.AWAITING_APPROVAL:
                raise conflict("invalid_state", f"No se puede aprobar en estado {task['state']}")
            if payload_sha256 != task["payload_sha256"] or payload_sha256 != c.task_digest(task["action"], json.loads(task["params"]), task["target_device_id"]):
                raise conflict("payload_mismatch", "La huella no coincide con el contenido actual de la tarea")
            now = self.clock()
            approval_id = "apr_" + uuid.uuid4().hex
            db.execute("INSERT INTO approvals VALUES (?,?,?,?,?,?,?,NULL,NULL)",
                       (approval_id, task_id, user_id, payload_sha256, channel, now, now + ttl_seconds))
            self._transition(task, c.APPROVED, f"{channel}:{user_id}", f"approval:{approval_id}")
            return self.public_task(self._task(user_id, task_id))

    def reject(self, user_id, task_id):
        return self._user_close(user_id, task_id, (c.AWAITING_APPROVAL,), c.REJECTED)

    def cancel(self, user_id, task_id):
        return self._user_close(user_id, task_id, c.CANCELLABLE, c.CANCELLED)

    def _user_close(self, user_id, task_id, allowed, to_state):
        with self.tx() as db:
            task = self._task(user_id, task_id)
            if task["state"] not in allowed:
                raise conflict("invalid_state", f"No se puede pasar de {task['state']} a {to_state}")
            db.execute("UPDATE approvals SET revoked_at=? WHERE task_id=? AND consumed_at IS NULL AND revoked_at IS NULL", (self.clock(), task_id))
            self._transition(task, to_state, f"user:{user_id}", lease_id=None, lease_device_id=None, lease_expires_at=None)
            return self.public_task(self._task(user_id, task_id))

    def resolve(self, user_id, task_id, outcome, note=None):
        """Human closes an uncertain execution after checking the PC."""
        if outcome not in (c.SUCCEEDED, c.FAILED):
            raise RelayError(400, "invalid_outcome", "outcome debe ser succeeded o failed")
        with self.tx():
            task = self._task(user_id, task_id)
            if task["state"] != c.UNKNOWN:
                raise conflict("invalid_state", "Solo se resuelven tareas en estado unknown")
            self._transition(task, outcome, f"user:{user_id}", (note or "resolved_by_user")[:500])
            return self.public_task(self._task(user_id, task_id))

    def retry(self, user_id, task_id, client_request_id, acknowledge_possible_duplicate=False):
        """New task with the same content; always needs a fresh approval."""
        with self.tx():
            task = self._task(user_id, task_id)
        if task["state"] not in (c.FAILED, c.UNKNOWN, c.CANCELLED):
            raise conflict("invalid_state", "Solo se reintenta una tarea failed, unknown o cancelled")
        if task["state"] == c.UNKNOWN and acknowledge_possible_duplicate is not True:
            raise conflict("possible_duplicate", "El resultado anterior es desconocido; confirmar que se acepta un posible duplicado")
        return self.create_task(user_id, client_request_id, task["action"], json.loads(task["params"]),
                                task["target_device_id"], channel="api", retry_of=task_id)

    # --- tasks: device side -----------------------------------------------------------

    def claim(self, user_id, device_id, max_tasks=1):
        max_tasks = max(1, min(int(max_tasks), 10))
        now = self.clock()
        claimed = []
        with self.tx() as db:
            rows = db.execute("""SELECT * FROM tasks WHERE user_id=? AND state=? AND (target_device_id IS NULL OR target_device_id=?)
                ORDER BY created_at LIMIT ?""", (user_id, c.APPROVED, device_id, max_tasks)).fetchall()
            for task in rows:
                approval = self._valid_approval(task, now)
                if not approval:
                    continue
                lease_id = "lse_" + uuid.uuid4().hex
                self._transition(task, c.CLAIMED, f"device:{device_id}", lease_id=lease_id, lease_device_id=device_id,
                                 lease_expires_at=now + self.claim_lease_seconds, attempts=task["attempts"] + 1)
                item = self.public_task(self._task(user_id, task["id"]))
                item["approval"] = {"id": approval["id"], "payload_sha256": approval["payload_sha256"], "expires_at": approval["expires_at"]}
                claimed.append(item)
        return claimed

    def _leased(self, user_id, device_id, task_id, lease_id):
        task = self.db.execute("SELECT * FROM tasks WHERE id=? AND user_id=? AND lease_device_id=?", (task_id, user_id, device_id)).fetchone()
        if not task:
            raise not_found()
        if task["lease_id"] != lease_id:
            raise conflict("lease_lost", "La reserva ya no pertenece a este dispositivo")
        return task

    def heartbeat(self, user_id, device_id, task_id, lease_id):
        now = self.clock()
        with self.tx():
            task = self._leased(user_id, device_id, task_id, lease_id)
            if task["state"] not in (c.CLAIMED, c.RUNNING):
                raise conflict("lease_lost", f"La tarea está en {task['state']}")
            seconds = self.claim_lease_seconds if task["state"] == c.CLAIMED else self.run_lease_seconds
            self.db.execute("UPDATE tasks SET lease_expires_at=? WHERE id=?", (now + seconds, task_id))
            return {"lease_expires_at": now + seconds, "state": task["state"]}

    def start(self, user_id, device_id, task_id, lease_id, payload_sha256):
        """Last server-side gate before any effect: lease, live approval, exact content."""
        now = self.clock()
        expired = False
        with self.tx() as db:
            task = self._leased(user_id, device_id, task_id, lease_id)
            if task["state"] == c.RUNNING:
                return self.public_task(task)  # retried start after a lost response
            if task["state"] != c.CLAIMED:
                raise conflict("invalid_state", f"La tarea está en {task['state']}")
            digest = c.task_digest(task["action"], json.loads(task["params"]), task["target_device_id"])
            if not payload_sha256 == task["payload_sha256"] == digest:
                raise conflict("payload_mismatch", "El contenido no coincide con lo aprobado")
            approval = self._valid_approval(task, now)
            if approval:
                db.execute("UPDATE approvals SET consumed_at=? WHERE id=?", (now, approval["id"]))
                self._transition(task, c.RUNNING, f"device:{device_id}", f"approval_consumed:{approval['id']}",
                                 lease_expires_at=now + self.run_lease_seconds)
                return self.public_task(self._task(user_id, task_id))
            # Commit the release before refusing, so the task is visible as needing approval.
            self._transition(task, c.AWAITING_APPROVAL, f"device:{device_id}", "approval_expired",
                             lease_id=None, lease_device_id=None, lease_expires_at=None)
            expired = True
        if expired:
            raise conflict("approval_expired", "La aprobación venció o fue revocada; se requiere una nueva")

    def complete(self, user_id, device_id, task_id, lease_id, outcome, result=None):
        if outcome not in c.DEVICE_OUTCOMES:
            raise RelayError(400, "invalid_outcome", "outcome debe ser succeeded, failed o unknown")
        result = c.validate_result(result)
        result_sha = hashlib.sha256(c.canonical({"outcome": outcome, "result": result})).hexdigest()
        with self.tx():
            task = self._leased(user_id, device_id, task_id, lease_id)
            if task["state"] in c.TERMINAL:
                if task["result_sha256"] == result_sha:
                    return self.public_task(task)  # idempotent re-send
                raise conflict("already_final", f"La tarea ya terminó en {task['state']}")
            if task["state"] == c.CLAIMED and outcome != c.FAILED:
                raise conflict("not_started", "Sin start confirmado solo se puede informar failed (sin efecto)")
            if task["state"] == c.UNKNOWN and task["result_sha256"] == result_sha:
                return self.public_task(task)
            if task["state"] not in (c.CLAIMED, c.RUNNING, c.UNKNOWN):
                raise conflict("invalid_state", f"La tarea está en {task['state']}")
            # Late reports are accepted on unknown: real evidence beats a timeout.
            self._transition(task, outcome, f"device:{device_id}", result.get("message", "")[:500] or None,
                             result=json.dumps(result, ensure_ascii=False), result_sha256=result_sha, lease_expires_at=None)
            return self.public_task(self._task(user_id, task_id))

    def device_task(self, user_id, device_id, task_id):
        with self.tx():
            task = self.db.execute("SELECT * FROM tasks WHERE id=? AND user_id=? AND lease_device_id=?", (task_id, user_id, device_id)).fetchone()
            if not task:
                raise not_found()
            return self.public_task(task)

    @staticmethod
    def public_task(row):
        task = {key: row[key] for key in ("id", "target_device_id", "client_request_id", "channel", "action", "payload_sha256",
                                          "state", "state_reason", "retry_of", "lease_id", "lease_expires_at", "attempts",
                                          "created_at", "updated_at", "version")}
        task["params"] = json.loads(row["params"])
        task["result"] = json.loads(row["result"]) if row["result"] else None
        return task
