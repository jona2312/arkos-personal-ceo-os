"""Gateway ledger: idempotency per (user, request_id) and budget reservations, in SQLite.

Every provider call is preceded by a committed reservation of its worst-case cost. The
row is marked 'sent' (committed) before the call leaves; a crash after that point leaves
'sent', which recovery turns into 'uncertain', never into a retry.
"""
import functools
import json
from pathlib import Path
import sqlite3
import threading
import time

IN_FLIGHT = ("reserved", "sent")
FINAL = ("completed", "failed", "cancelled", "uncertain", "reconciled")


def _serialized(method):
    """One connection shared by gateway threads: serialize every public operation."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


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
        self.db.execute("""CREATE TABLE IF NOT EXISTS calls (
            user_id TEXT NOT NULL, request_id TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL,
            day TEXT NOT NULL, reserved INTEGER NOT NULL, charged INTEGER NOT NULL DEFAULT 0,
            cancel_requested INTEGER NOT NULL DEFAULT 0, response TEXT,
            created REAL NOT NULL, updated REAL NOT NULL, PRIMARY KEY (user_id, request_id))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS spend (
            scope TEXT NOT NULL, day TEXT NOT NULL, reserved INTEGER NOT NULL DEFAULT 0,
            charged INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (scope, day))""")

    @_serialized
    def close(self):
        self.db.close()

    def _tx(self):
        self.db.execute("BEGIN IMMEDIATE")

    def _row(self, user, rid):
        row = self.db.execute("SELECT * FROM calls WHERE user_id=? AND request_id=?", (user, rid)).fetchone()
        return dict(row) if row else None

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

    def _used(self, scope, day):
        row = self.db.execute("SELECT reserved+charged FROM spend WHERE scope=? AND day=?", (scope, day)).fetchone()
        return row[0] if row else 0

    @_serialized
    def spend(self, scope, day):
        row = self.db.execute("SELECT reserved, charged FROM spend WHERE scope=? AND day=?", (scope, day)).fetchone()
        return dict(reserved=row[0], charged=row[1]) if row else dict(reserved=0, charged=0)

    @_serialized
    def reserve(self, user, rid, digest, amount, day, user_limit, global_limit):
        """Returns (created, row). Raises LedgerError for conflict, busy or budget."""
        self._tx()
        try:
            row = self._row(user, rid)
            if row:
                self.db.execute("ROLLBACK")
                if row["digest"] != digest:
                    raise LedgerError("conflict", "Ese request_id ya corresponde a otro pedido")
                return False, self.get(user, rid)
            busy = self.db.execute("SELECT 1 FROM calls WHERE user_id=? AND state IN (?,?)",
                                   (user, *IN_FLIGHT)).fetchone()
            if busy:
                raise LedgerError("busy", "Ya hay un pedido Cloud en curso para este usuario")
            if (self._used("user:" + user, day) + amount > user_limit
                    or self._used("global", day) + amount > global_limit):
                raise LedgerError("budget_exhausted", "Presupuesto diario insuficiente para este pedido")
            now = time.time()
            self.db.execute("INSERT INTO calls (user_id, request_id, digest, state, day, reserved, created, updated) "
                            "VALUES (?,?,?,?,?,?,?,?)", (user, rid, digest, "reserved", day, amount, now, now))
            self._spend("user:" + user, day, reserved=amount)
            self._spend("global", day, reserved=amount)
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        return True, self.get(user, rid)

    def _release(self, row, charged):
        for scope in ("user:" + row["user_id"], "global"):
            self._spend(scope, row["day"], reserved=-row["reserved"], charged=charged)

    def _set(self, row, state, charged=None, response=None, keep_reservation=False):
        if not keep_reservation:
            self._release(row, charged or 0)
        self.db.execute("UPDATE calls SET state=?, charged=?, response=?, reserved=?, updated=? "
                        "WHERE user_id=? AND request_id=?",
                        (state, charged or 0, json.dumps(response, ensure_ascii=False) if response else None,
                         row["reserved"] if keep_reservation else 0, time.time(), row["user_id"], row["request_id"]))

    @_serialized
    def mark_sent(self, user, rid):
        """Commit 'sent' before the provider call. False if it was cancelled first (released)."""
        self._tx()
        row = self._row(user, rid)
        if row["state"] != "reserved" or row["cancel_requested"]:
            if row["state"] == "reserved":
                self._set(row, "cancelled")
            self.db.execute("COMMIT")
            return False
        self.db.execute("UPDATE calls SET state='sent', updated=? WHERE user_id=? AND request_id=?",
                        (time.time(), user, rid))
        self.db.execute("COMMIT")
        return True

    @_serialized
    def settle(self, user, rid, outcome, charged=0, response=None):
        """outcome: completed | not_charged | uncertain. A cancel request wins over 'completed'."""
        self._tx()
        row = self._row(user, rid)
        if row["state"] != "sent":
            self.db.execute("COMMIT")
            return self.get(user, rid)
        if outcome == "uncertain":
            self._set(row, "uncertain", keep_reservation=True)
        elif outcome == "not_charged":
            self._set(row, "cancelled" if row["cancel_requested"] else "failed")
        elif row["cancel_requested"]:
            self._set(row, "cancelled", charged=charged)  # paid, but the content is discarded
        else:
            self._set(row, "completed", charged=charged, response=response)
        self.db.execute("COMMIT")
        return self.get(user, rid)

    @_serialized
    def request_cancel(self, user, rid):
        self._tx()
        row = self._row(user, rid)
        if row is None:
            self.db.execute("ROLLBACK")
            return None
        if row["state"] == "reserved":
            self._set(row, "cancelled")
        elif row["state"] == "sent":
            self.db.execute("UPDATE calls SET cancel_requested=1, updated=? WHERE user_id=? AND request_id=?",
                            (time.time(), user, rid))
        self.db.execute("COMMIT")
        return self.get(user, rid)

    @_serialized
    def recover(self):
        """After a gateway restart: 'reserved' never left (release), 'sent' is uncertain (keep)."""
        self._tx()
        rows = [dict(r) for r in self.db.execute("SELECT * FROM calls WHERE state IN (?,?)", IN_FLIGHT)]
        for row in rows:
            if row["state"] == "reserved":
                self._set(row, "failed")
            else:
                self._set(row, "uncertain", keep_reservation=True)
        self.db.execute("COMMIT")
        return len(rows)

    @_serialized
    def reconcile(self, user, rid, charged):
        """Operator action with the provider's usage report: closes an uncertain reservation."""
        if type(charged) is not int or charged < 0:
            raise ValueError("Costo conciliado inválido")
        self._tx()
        row = self._row(user, rid)
        if row is None or row["state"] != "uncertain":
            self.db.execute("ROLLBACK")
            raise LedgerError("conflict", "Solo se concilian pedidos inciertos")
        self._set(row, "reconciled", charged=charged)
        self.db.execute("COMMIT")
        return self.get(user, rid)

    @_serialized
    def purge_content(self, older_than_s):
        """Retention: drop stored replies older than the window; keep billing metadata."""
        cutoff = time.time() - older_than_s
        self.db.execute("UPDATE calls SET response=NULL WHERE response IS NOT NULL AND updated < ?", (cutoff,))
