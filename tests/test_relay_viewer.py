"""Read-only sync for the PC screen. Synthetic data only. Reading must never cause execution."""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from arkos_relay import agent as ag
from arkos_relay import contract as c
from arkos_relay import viewer as vw
from tests.relay_support import InProcessTransport, RelayFixture


class ViewerFixture(RelayFixture):
    def setUp(self):
        super().setUp()
        self.device = self.pair(self.alice_token, "PC 1")
        self.viewer_token = self.issue_viewer(self.alice_token, self.device)
        self.view_dir = self.dir / "viewer"
        self.outputs = self.dir / "outputs"
        self.transport = InProcessTransport(self.app, self.viewer_token)
        self.viewer = self.new_viewer()

    def tearDown(self):
        self.viewer.close()
        super().tearDown()

    def new_viewer(self, transport=None, device=None):
        return vw.ViewerSync(transport or self.transport, self.view_dir, (device or self.device)["device_id"],
                             outputs_dir=self.outputs, clock=self.clock)

    def issue_viewer(self, user_token, device):
        status, code = self.call("POST", f"/v1/devices/{device['device_id']}/viewer-codes", {}, user_token)
        assert status == 201, code
        status, paired = self.call("POST", "/v1/viewer/pair", {"code": code["code"]})
        assert status == 201, paired
        return paired["viewer_token"]

    def states(self, snapshot):
        return {t["remote_id"]: t["state"] for t in snapshot["tasks"]}

    def device_call(self, method, path, body=None):
        return self.call(method, path, body, self.device["device_token"])

    def task(self, text, request_id, approve=False, **extra):
        task = self.create(self.alice_token, text=text, request_id=request_id, **extra)[1]["task"]
        if approve:
            self.assertEqual(self.approve(self.alice_token, task)[0], 200)
        return task


class CredentialTests(ViewerFixture, unittest.TestCase):
    def test_viewer_token_is_read_only_and_separate(self):
        task = self.task("Sintética", "req-v-0001", approve=True)
        self.assertEqual(self.call("POST", "/v1/agent/claim", {}, self.viewer_token)[0], 401)
        self.assertEqual(self.call("POST", f"/v1/agent/tasks/{task['id']}/start", {}, self.viewer_token)[0], 401)
        self.assertEqual(self.call("GET", "/v1/tasks", token=self.viewer_token)[0], 401)
        self.assertEqual(self.approve(self.viewer_token, task)[0], 401)
        self.assertEqual(self.call("POST", "/v1/tasks", {}, self.viewer_token)[0], 401)
        # The device token is not silently upgraded: it cannot read the queue nor mint a viewer code.
        self.assertEqual(self.device_call("GET", "/v1/viewer/tasks")[0], 401)
        self.assertEqual(self.device_call("POST", f"/v1/devices/{self.device['device_id']}/viewer-codes", {})[0], 401)

    def test_viewer_code_is_single_use_and_owner_bound(self):
        status, code = self.call("POST", f"/v1/devices/{self.device['device_id']}/viewer-codes", {}, self.alice_token)
        self.assertEqual(self.call("POST", "/v1/viewer/pair", {"code": code["code"]})[0], 201)
        self.assertEqual(self.call("POST", "/v1/viewer/pair", {"code": code["code"]})[0], 401)
        self.assertEqual(self.call("POST", f"/v1/devices/{self.device['device_id']}/viewer-codes", {}, self.bob_token)[0], 404)
        status, code = self.call("POST", f"/v1/devices/{self.device['device_id']}/viewer-codes", {}, self.alice_token)
        self.clock.advance(601)
        self.assertEqual(self.call("POST", "/v1/viewer/pair", {"code": code["code"]})[0], 401)

    def test_revocation_stops_reading(self):
        self.task("Sintética", "req-v-0001")
        self.assertEqual(self.viewer.sync()["sync"]["status"], "fresh")
        self.call("POST", f"/v1/devices/{self.device['device_id']}/viewer-tokens/revoke", {}, self.alice_token)
        snapshot = self.viewer.sync()
        self.assertEqual(snapshot["sync"]["status"], "unauthorized")
        other = self.issue_viewer(self.alice_token, self.device)
        self.call("POST", f"/v1/devices/{self.device['device_id']}/revoke", {}, self.alice_token)
        self.assertEqual(self.call("GET", "/v1/viewer/tasks", token=other)[0], 401)


class IsolationTests(ViewerFixture, unittest.TestCase):
    def test_users_and_devices_are_isolated(self):
        second = self.pair(self.alice_token, "PC 2")
        mine = self.task("Para PC 1", "req-v-0001", target_device_id=self.device["device_id"])
        other_pc = self.task("Para PC 2", "req-v-0002", target_device_id=second["device_id"])
        bob_device = self.pair(self.bob_token, "PC Bob")
        bob_task = self.create(self.bob_token, text="De Bob", request_id="req-v-bob1")[1]["task"]
        snapshot = self.viewer.sync()
        self.assertEqual(set(self.states(snapshot)), {mine["id"]})
        bob_viewer = vw.ViewerSync(InProcessTransport(self.app, self.issue_viewer(self.bob_token, bob_device)),
                                   self.dir / "bob-viewer", bob_device["device_id"], clock=self.clock)
        try:
            self.assertEqual(set(self.states(bob_viewer.sync())), {bob_task["id"]})
        finally:
            bob_viewer.close()
        second_viewer = vw.ViewerSync(InProcessTransport(self.app, self.issue_viewer(self.alice_token, second)),
                                      self.dir / "pc2-viewer", second["device_id"], clock=self.clock)
        try:
            self.assertEqual(set(self.states(second_viewer.sync())), {other_pc["id"]})
        finally:
            second_viewer.close()


class SnapshotTests(ViewerFixture, unittest.TestCase):
    def drive_all_states(self):
        """One synthetic task per state, reached through the real API."""
        ids = {}
        ids[c.AWAITING_APPROVAL] = self.task("Pendiente", "req-s-pend")["id"]
        ids[c.REJECTED] = self.task("Rechazada", "req-s-rej")["id"]
        self.call("POST", f"/v1/tasks/{ids[c.REJECTED]}/reject", {}, self.alice_token)
        ids[c.CANCELLED] = self.task("Cancelada", "req-s-can", approve=True)["id"]
        self.call("POST", f"/v1/tasks/{ids[c.CANCELLED]}/cancel", {}, self.alice_token)
        leased = {}
        for state in (c.SUCCEEDED, c.FAILED, c.UNKNOWN, c.RUNNING, c.CLAIMED):
            task = self.task(state, f"req-s-{state}", approve=True)
            claimed = self.device_call("POST", "/v1/agent/claim", {})[1]["tasks"][0]
            ids[state], leased[state] = task["id"], (claimed, task)
            if state != c.CLAIMED:
                self.device_call("POST", f"/v1/agent/tasks/{task['id']}/start",
                                 {"lease_id": claimed["lease_id"], "payload_sha256": task["payload_sha256"]})
            if state in (c.SUCCEEDED, c.FAILED, c.UNKNOWN):
                self.device_call("POST", f"/v1/agent/tasks/{task['id']}/complete",
                                 {"lease_id": claimed["lease_id"], "outcome": state, "result": {"message": f"Sintético {state}"}})
        ids[c.APPROVED] = self.task("Aprobada sin reservar", "req-s-appr", approve=True)["id"]
        return ids

    def test_snapshot_keeps_every_state(self):
        ids = self.drive_all_states()
        snapshot = self.viewer.sync()
        self.assertEqual(self.states(snapshot), {task_id: state for state, task_id in ids.items()})
        cards = {t["remote_id"]: t for t in snapshot["tasks"]}
        self.assertIsNotNone(cards[ids[c.APPROVED]]["approval_expires_at"])
        self.assertIsNone(cards[ids[c.AWAITING_APPROVAL]]["approval_expires_at"])
        # Active work is listed before finished work.
        order = [t["state"] for t in snapshot["tasks"]]
        self.assertTrue(all(s in vw.ACTIVE for s in order[:5]), order)

    def test_pending_tasks_not_yet_delivered_are_visible(self):
        waiting = self.task("Esperando aprobación", "req-v-0001")
        approved = self.task("Aprobada, PC sin reclamar", "req-v-0002", approve=True)
        snapshot = self.viewer.sync()
        self.assertEqual(self.states(snapshot), {waiting["id"]: c.AWAITING_APPROVAL, approved["id"]: c.APPROVED})
        card = next(t for t in snapshot["tasks"] if t["remote_id"] == waiting["id"])
        self.assertEqual((card["origin"], card["action"], card["summary"]["title"]), ("relay", "note.create", "Esperando aprobación"))

    def test_reading_never_approves_claims_or_executes(self):
        approved = self.task("Aprobada", "req-v-0001", approve=True)
        waiting = self.task("Pendiente", "req-v-0002")
        for _ in range(3):
            self.viewer.sync()
            vw.read_snapshot(self.viewer.snapshot_path, now=self.clock())
        self.assertEqual({m for m, _ in self.transport.calls}, {"GET"})
        self.assertTrue(all(p.startswith("/v1/viewer/tasks") for _, p in self.transport.calls))
        self.assertEqual(self.store.get_task(self.alice, approved["id"])["state"], c.APPROVED)
        self.assertEqual(self.store.get_task(self.alice, approved["id"])["attempts"], 0)
        self.assertEqual(self.store.get_task(self.alice, waiting["id"])["state"], c.AWAITING_APPROVAL)
        consumed = self.store.db.execute("SELECT COUNT(*) FROM approvals WHERE consumed_at IS NOT NULL").fetchone()[0]
        self.assertEqual(consumed, 0)
        actors = {r[0] for r in self.store.db.execute("SELECT actor FROM task_events")}
        self.assertFalse(any(a.startswith("device:") for a in actors), actors)
        self.assertFalse(self.outputs.exists())
        # Nothing is copied into arkos_pilot.Queue or the agent journal.
        self.assertEqual(sorted(p.name for p in self.dir.rglob("*.sqlite3")), ["relay.sqlite3", "viewer.sqlite3"])

    def test_incremental_sync(self):
        first = self.task("Uno", "req-v-0001")
        self.task("Dos", "req-v-0002")
        self.viewer.sync()
        cursor = self.viewer._get("cursor")
        self.transport.calls.clear()
        self.assertEqual(self.store.viewer_tasks(self.alice, self.device["device_id"], cursor)["tasks"], [])
        self.approve(self.alice_token, first)
        page = self.store.viewer_tasks(self.alice, self.device["device_id"], cursor)
        self.assertEqual([t["id"] for t in page["tasks"]], [first["id"]])
        snapshot = self.viewer.sync()
        self.assertEqual(self.transport.calls, [("GET", f"/v1/viewer/tasks?after_version={cursor}&limit=200")])
        self.assertEqual(self.states(snapshot)[first["id"]], c.APPROVED)
        self.assertEqual(snapshot["task_count"], 2)

    def test_pagination(self):
        for i in range(7):
            self.task(f"Nota {i}", f"req-page-{i:03d}")
        self.viewer.close()
        self.viewer = vw.ViewerSync(self.transport, self.view_dir, self.device["device_id"], clock=self.clock, page_size=3)
        self.assertEqual(self.viewer.sync()["task_count"], 7)
        self.assertEqual(len(self.transport.calls), 3)

    def test_survives_restart_and_disconnection(self):
        task = self.task("Persistente", "req-v-0001")
        self.viewer.sync()
        last_success = self.viewer._get("last_success_at")
        self.viewer.close()
        self.transport.offline = True
        self.viewer = self.new_viewer()
        self.clock.advance(30)
        snapshot = self.viewer.sync()
        self.assertEqual(snapshot["sync"]["status"], "offline")
        self.assertEqual(snapshot["sync"]["last_success_at"], last_success)
        self.assertEqual(self.states(snapshot), {task["id"]: c.AWAITING_APPROVAL})
        self.transport.offline = False
        self.approve(self.alice_token, task)
        snapshot = self.viewer.sync()
        self.assertEqual((snapshot["sync"]["status"], self.states(snapshot)[task["id"]]), ("fresh", c.APPROVED))

    def test_server_restart_and_database_replacement(self):
        task = self.task("Antes del reinicio", "req-v-0001")
        self.viewer.sync()
        self.restart_server()
        self.transport.app = self.app
        self.assertEqual(self.states(self.viewer.sync()), {task["id"]: c.AWAITING_APPROVAL})
        # Relay restored from an older backup (same credentials, version head goes backwards): full rebuild.
        self.store.db.execute("DELETE FROM task_events")
        self.store.db.execute("DELETE FROM tasks")
        self.store.db.execute("UPDATE meta SET value=0 WHERE key='version'")
        restored = self.task("Después de restaurar", "req-v-0002")
        self.assertEqual(self.store.viewer_tasks(self.alice, self.device["device_id"])["head_version"], 1)  # == old cursor
        self.clock.advance(vw.FULL_RESYNC_SECONDS + 1)
        snapshot = self.viewer.sync()
        self.assertEqual(self.states(snapshot), {restored["id"]: c.AWAITING_APPROVAL})  # old rows not kept

    def test_version_regression_triggers_immediate_rebuild(self):
        self.task("Uno", "req-v-0001")
        self.task("Dos", "req-v-0002")
        self.viewer.sync()
        self.store.db.execute("DELETE FROM task_events")
        self.store.db.execute("DELETE FROM tasks")
        self.store.db.execute("UPDATE meta SET value=0 WHERE key='version'")
        self.assertEqual(self.viewer.sync()["tasks"], [])

    def test_cut_during_full_resync_keeps_previous_mirror(self):
        for i in range(5):
            self.task(f"Nota {i}", f"req-cut-{i:03d}")
        self.viewer.sync()
        self.viewer.close()
        original = self.transport.__call__
        calls = []

        def flaky(method, path, body=None):
            calls.append(path)
            if len(calls) == 2:
                raise ag.TransportError("cut mid-pagination")
            return original(method, path, body)
        self.viewer = vw.ViewerSync(flaky, self.view_dir, self.device["device_id"], clock=self.clock, page_size=2)
        snapshot = self.viewer.sync()
        self.assertEqual((snapshot["sync"]["status"], snapshot["task_count"]), ("offline", 5))

    def test_stale_and_never_synced(self):
        self.transport.offline = True
        self.assertEqual(self.viewer.sync()["sync"]["status"], "never_synced")
        self.transport.offline = False
        self.assertEqual(self.viewer.sync()["sync"]["status"], "fresh")
        self.clock.advance(vw.STALE_AFTER_SECONDS + 1)
        self.assertEqual(self.viewer.write_snapshot()["sync"]["status"], "stale")
        # A reader recomputes freshness with its own clock even if the file says "fresh".
        self.viewer.sync()
        later = self.clock() + vw.STALE_AFTER_SECONDS + 5
        self.assertEqual(vw.read_snapshot(self.viewer.snapshot_path, now=later)["sync"]["status"], "stale")

    def test_snapshot_contains_no_secrets(self):
        self.drive_all_states()
        self.viewer.sync()
        raw = self.viewer.snapshot_path.read_text(encoding="utf-8")
        for secret in ("akd_", "akr_", "aku_", "lse_", "lease_id", "client_request_id", self.viewer_token, self.device["device_token"]):
            self.assertNotIn(secret, raw)
        snapshot = json.loads(raw)
        self.assertEqual((snapshot["schema"], snapshot["schema_version"], snapshot["source"]), (vw.SCHEMA, 1, "relay"))

    def test_size_limits_and_previews(self):
        for i in range(vw.MAX_TASKS + 20):
            self.store.create_task(self.alice, f"req-big-{i:04d}", "note.create", {"text": "x" * 5000})
        snapshot = self.viewer.sync()
        self.assertTrue(snapshot["truncated"])
        self.assertLessEqual(snapshot["task_count"], vw.MAX_TASKS)
        self.assertLessEqual(self.viewer.snapshot_path.stat().st_size, vw.MAX_BYTES)
        self.assertTrue(all(len(t["summary"]["preview"]) <= vw.PREVIEW_CHARS for t in snapshot["tasks"]))

    def test_atomic_write_keeps_previous_snapshot_on_failure(self):
        self.task("Primera", "req-v-0001")
        self.viewer.sync()
        before = self.viewer.snapshot_path.read_bytes()
        self.task("Segunda", "req-v-0002")
        with patch("arkos_relay.viewer.os.replace", side_effect=PermissionError("locked by reader")), \
                patch("arkos_relay.viewer.time.sleep"):
            with self.assertRaises(PermissionError):
                self.viewer.sync()
        self.assertEqual(self.viewer.snapshot_path.read_bytes(), before)
        self.assertEqual([p.name for p in self.view_dir.iterdir() if p.name.startswith(".snapshot-")], [])
        self.assertEqual(self.viewer.sync()["task_count"], 2)

    def test_artifact_availability(self):
        task = self.task("Resultado sintético", "req-v-0001", approve=True)
        journal = ag.Journal(self.dir / "journal.sqlite3")
        try:
            ag.Agent(InProcessTransport(self.app, self.device["device_token"]), self.device["device_id"], journal,
                     ag.Executor(self.outputs, {}), clock=self.clock).run_once()
        finally:
            journal.close()
        artifact = next(t for t in self.viewer.sync()["tasks"] if t["remote_id"] == task["id"])["artifact"]
        self.assertEqual((artifact["status"], artifact["relative_path"]), ("available", f"notes/{task['id']}.md"))
        path = self.outputs / artifact["relative_path"]
        path.write_bytes(b"alterado y mas largo")
        self.assertEqual(self.viewer.write_snapshot()["tasks"][0]["artifact"]["status"], "mismatch")
        os.remove(path)
        self.assertEqual(self.viewer.write_snapshot()["tasks"][0]["artifact"]["status"], "missing")


if __name__ == "__main__":
    unittest.main()
