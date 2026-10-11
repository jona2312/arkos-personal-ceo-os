"""Gateway ledger: device tokens, idempotency per (user, request_id) and budget, in SQLite.

Every provider call is preceded by a committed reservation of its worst-case cost. The
row is marked 'sent' (committed) before the call leaves; a crash after that point leaves
'sent', which recovery turns into 'uncertain', never into a retry. Reservations that are
still open (in flight or uncertain) keep counting against later days until reconciled.

Several connections (threads or operator processes) may use the same file: every write
runs in BEGIN IMMEDIATE. Only one *gateway* may run recovery; see gateway.InstanceLock.
"""
from contextlib import contextmanager
import functools
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time

SCHEMA_VERSION = 2
OPEN = ("reserved", "sent", "uncertain")   # reservations not yet settled
IN_FLIGHT = ("reserved", "sent")
CANCELLED_BEFORE_ARRIVAL = "-"  # never a sha256 digest
FINAL = ("completed", "failed", "cancelled", "uncertain", "reconciled")


def _serialized(method):
    """One connection shared by gateway threads: serialize every public operation."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LedgerError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Ledger:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            self.db.close()
            raise RuntimeError(f"Ledger con esquema {version}; este gateway usa {SCHEMA_VERSION}. No se modifica.")
        with self._transaction():
            self.db.execute("""CREATE TABLE IF NOT EXISTS calls (
                user_id TEXT NOT NULL, request_id TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL,
                day TEXT NOT NULL, reserved INTEGER NOT NULL, charged INTEGER NOT NULL DEFAULT 0,
                cancel_requested INTEGER NOT NULL DEFAULT 0, overrun INTEGER NOT NULL DEFAULT 0, response TEXT,
                created REAL NOT NULL, updated REAL NOT NULL, PRIMARY KEY (user_id, request_id))""")
            self.db.execute("""CREATE TABLE IF NOT EXISTS spend (
                scope TEXT NOT NULL, day TEXT NOT NULL, reserved INTEGER NOT NULL DEFAULT 0,
                charged INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (scope, day))""")
            self.db.execute("""CREATE TABLE IF NOT EXISTS tokens (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, created REAL NOT NULL, revoked REAL)""")
            self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    @_serialized
    def close(self):
        self.db.close()

    @contextmanager
    def _transaction(self):
        """BEGIN IMMEDIATE ... COMMIT, rolled back on any exception (never left open)."""
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    def _row(self, user, rid):
        row = self.db.execute("SELECT * FROM calls WHERE user_id=? AND request_id=?", (user, rid)).fetchone()
        return dict(row) if row else None

    def _need(self, user, rid):
        row = self._row(user, rid)
        if row is None:
            raise LedgerError("not_found", "Pedido inexistente")
        return row

    # --- device tokens (hash only; the plain token is shown once to the operator) -----
    @_serialized
    def issue_token(self, user):
        if not isinstance(user, str) or not 1 <= len(user) <= 64:
            raise ValueError("Usuario inválido")
        token = "akc_" + secrets.token_urlsafe(32)
        with self._transaction():
            self.db.execute("INSERT INTO tokens VALUES (?,?,?,NULL)", (token_hash(token), user, time.time()))
        return token

    @_serialized
    def register_token_hash(self, digest, user):
        with self._transaction():
            self.db.execute("INSERT OR IGNORE INTO tokens VALUES (?,?,?,NULL)", (digest, user, time.time()))

    @_serialized
    def revoke_token(self, digest):
        with self._transaction():
            return self.db.execute("UPDATE tokens SET revoked=? WHERE token_hash=? AND revoked IS NULL",
                                   (time.time(), digest)).rowcount > 0

    @_serialized
    def revoke_user(self, user):
        with self._transaction():
            return self.db.execute("UPDATE tokens SET revoked=? WHERE user_id=? AND revoked IS NULL",
                                   (time.time(), user)).rowcount

    @_serialized
    def revoke_prefix(self, prefix):
        """Revoke the single active token whose hash starts with prefix (as listed by tokens())."""
        if not isinstance(prefix, str) or len(prefix) < 8:
            raise ValueError("Prefijo de al menos 8 caracteres")
        with self._transaction():
            rows = self.db.execute("SELECT token_hash FROM tokens WHERE token_hash LIKE ? AND revoked IS NULL",
                                   (prefix.lower() + "%",)).fetchall()
            if len(rows) != 1:
                raise LedgerError("conflict", f"El prefijo coincide con {len(rows)} tokens activos")
            self.db.execute("UPDATE tokens SET revoked=? WHERE token_hash=?", (time.time(), rows[0][0]))
        return True

    @_serialized
    def user_for(self, digest):
        row = self.db.execute("SELECT user_id FROM tokens WHERE token_hash=? AND revoked IS NULL", (digest,)).fetchone()
        return row[0] if row else None

    @_serialized
    def tokens(self):
        return [dict(user_id=r[0], token_prefix=r[1][:8], revoked=r[2] is not None)
                for r in self.db.execute("SELECT user_id, token_hash, revoked FROM tokens ORDER BY created")]

    # --- reads ------------------------------------------------------------------------
    @_serialized
    def get(self, user, rid):
        row = self._row(user, rid)
        if row and row["response"]:
            row["response"] = json.loads(row["response"])
        return row

    def _spend(self, scope, day, reserved=0, charged=0):
        self.db.execute("INSERT OR IGNORE INTO spend (scope, day) VALUES (?,?)", (scope, day))
        self.db.execute("UPDATE spend SET reserved=reserved+?, charged=charged+? WHERE scope=? AND day=?",
                        (reserved, charged, scope, day))

    def _exposure(self, user, day):
        """Today's reserved+charged plus every still-open reservation from earlier days."""
        scope = "global" if user is None else "user:" + user
        row = self.db.execute("SELECT reserved+charged FROM spend WHERE scope=? AND day=?", (scope, day)).fetchone()
        carried = self.db.execute(
            "SELECT COALESCE(SUM(reserved),0) FROM calls WHERE day<? AND state IN (?,?,?)"
            + ("" if user is None else " AND user_id=?"),
            (day, *OPEN) + (() if user is None else (user,))).fetchone()[0]
        return (row[0] if row else 0) + carried

    def _month_exposure(self, day):
        """Global reserved+charged this UTC month plus open reservations from earlier months."""
        month_start = day[:8] + "01"
        this_month = self.db.execute("SELECT COALESCE(SUM(reserved+charged),0) FROM spend "
                                     "WHERE scope='global' AND day>=? AND day<=?", (month_start, day)).fetchone()[0]
        carried = self.db.execute("SELECT COALESCE(SUM(reserved),0) FROM calls WHERE day<? AND state IN (?,?,?)",
                                  (month_start, *OPEN)).fetchone()[0]
        return this_month + carried

    @_serialized
    def month_spend(self, day):
        month_start = day[:8] + "01"
        row = self.db.execute("SELECT COALESCE(SUM(reserved),0), COALESCE(SUM(charged),0) FROM spend "
                              "WHERE scope='global' AND day>=? AND day<=?", (month_start, day)).fetchone()
        return dict(reserved=row[0], charged=row[1])

    @_serialized
    def spend(self, scope, day):
        row = self.db.execute("SELECT reserved, charged FROM spend WHERE scope=? AND day=?", (scope, day)).fetchone()
        return dict(reserved=row[0], charged=row[1]) if row else dict(reserved=0, charged=0)

    @_serialized
    def open_reservations(self, user=None):
        query = "SELECT COALESCE(SUM(reserved),0) FROM calls WHERE state IN (?,?,?)"
        return self.db.execute(query + ("" if user is None else " AND user_id=?"),
                               OPEN + (() if user is None else (user,))).fetchone()[0]

    # --- lifecycle ----------------------------------------------------------------------
    @_serialized
    def reserve(self, user, rid, digest, amount, day, user_limit, global_limit, monthly_limit=None):
        """Returns (created, row). Raises LedgerError for conflict, busy or budget.

        day is 'YYYY-MM-DD' (UTC). monthly_limit caps the global spend of that calendar month."""
        with self._transaction():
            row = self._row(user, rid)
            if row:
                if row["digest"] != digest:
                    raise LedgerError("conflict", "Ese request_id ya corresponde a otro pedido")
                created = False
            else:
                if self.db.execute("SELECT 1 FROM calls WHERE user_id=? AND state IN (?,?)",
                                   (user, *IN_FLIGHT)).fetchone():
                    raise LedgerError("busy", "Ya hay un pedido Cloud en curso para este usuario")
                if (self._exposure(user, day) + amount > user_limit
                        or self._exposure(None, day) + amount > global_limit
                        or (monthly_limit is not None and self._month_exposure(day) + amount > monthly_limit)):
                    raise LedgerError("budget_exhausted", "Presupuesto insuficiente para este pedido")
                now = time.time()
                self.db.execute("INSERT INTO calls (user_id, request_id, digest, state, day, reserved, created, updated) "
                                "VALUES (?,?,?,?,?,?,?,?)", (user, rid, digest, "reserved", day, amount, now, now))
                self._spend("user:" + user, day, reserved=amount)
                self._spend("global", day, reserved=amount)
                created = True
        return created, self.get(user, rid)

    def _release(self, row, charged):
        for scope in ("user:" + row["user_id"], "global"):
            self._spend(scope, row["day"], reserved=-row["reserved"], charged=charged)

    def _set(self, row, state, charged=0, response=None, keep_reservation=False, overrun=False):
        if not keep_reservation:
            self._release(row, charged)
        self.db.execute("UPDATE calls SET state=?, charged=?, response=?, reserved=?, overrun=?, updated=? "
                        "WHERE user_id=? AND request_id=?",
                        (state, charged, json.dumps(response, ensure_ascii=False) if response else None,
                         row["reserved"] if keep_reservation else 0, int(overrun), time.time(),
                         row["user_id"], row["request_id"]))

    @_serialized
    def mark_sent(self, user, rid):
        """Commit 'sent' before the provider call. False if it was cancelled first (released)."""
        with self._transaction():
            row = self._need(user, rid)
            if row["state"] != "reserved":
                return False
            if row["cancel_requested"]:
                self._set(row, "cancelled")
                return False
            self.db.execute("UPDATE calls SET state='sent', updated=? WHERE user_id=? AND request_id=?",
                            (time.time(), user, rid))
            return True

    @_serialized
    def settle(self, user, rid, outcome, charged=0, response=None):
        """outcome: completed | not_charged | uncertain. A cancel request wins over 'completed'."""
        with self._transaction():
            row = self._need(user, rid)
            if row["state"] != "sent":
                raise LedgerError("conflict", f"Liquidación inesperada en estado {row['state']}")
            overrun = charged > row["reserved"]
            if outcome == "uncertain":
                self._set(row, "uncertain", keep_reservation=True)
            elif outcome == "not_charged":
                self._set(row, "cancelled" if row["cancel_requested"] else "failed")
            elif row["cancel_requested"]:
                self._set(row, "cancelled", charged=charged, overrun=overrun)  # paid; content discarded
            else:
                self._set(row, "completed", charged=charged, response=response, overrun=overrun)
        return self.get(user, rid)

    @_serialized
    def request_cancel(self, user, rid, day=None):
        """With day=..., a cancel for an unknown id leaves a tombstone: if the request arrives
        later (the cancel overtook it), reserve() sees a different digest and refuses it."""
        with self._transaction():
            row = self._row(user, rid)
            if row is None:
                if day is None:
                    return None
                now = time.time()
                self.db.execute("INSERT INTO calls (user_id, request_id, digest, state, day, reserved, created, updated) "
                                "VALUES (?,?,?,?,?,0,?,?)", (user, rid, CANCELLED_BEFORE_ARRIVAL, "cancelled", day, now, now))
                return self._row(user, rid)
            if row["state"] == "reserved":
                self._set(row, "cancelled")
            elif row["state"] == "sent":
                self.db.execute("UPDATE calls SET cancel_requested=1, updated=? WHERE user_id=? AND request_id=?",
                                (time.time(), user, rid))
        return self.get(user, rid)

    @_serialized
    def recover(self):
        """Gateway start only (under the instance lock): 'reserved' never left, 'sent' is uncertain."""
        with self._transaction():
            rows = [dict(r) for r in self.db.execute("SELECT * FROM calls WHERE state IN (?,?)", IN_FLIGHT)]
            for row in rows:
                if row["state"] == "reserved":
                    self._set(row, "failed")
                else:
                    self._set(row, "uncertain", keep_reservation=True)
        return len(rows)

    @_serialized
    def reconcile(self, user, rid, charged):
        """Operator action with the provider's usage report: closes an uncertain reservation."""
        if type(charged) is not int or charged < 0:
            raise ValueError("Costo conciliado inválido")
        with self._transaction():
            row = self._row(user, rid)
            if row is None or row["state"] != "uncertain":
                raise LedgerError("conflict", "Solo se concilian pedidos inciertos")
            self._set(row, "reconciled", charged=charged)
        return self.get(user, rid)

    @_serialized
    def purge_content(self, older_than_s, now=None):
        """Retention: drop stored replies older than the window; keep billing metadata."""
        cutoff = (time.time() if now is None else now) - older_than_s
        with self._transaction():
            return self.db.execute("UPDATE calls SET response=NULL WHERE response IS NOT NULL AND updated <= ?",
                                   (cutoff,)).rowcount
