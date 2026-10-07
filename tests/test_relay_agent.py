"""End-to-end: phone creates and approves while the PC is off; the agent syncs later."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import unittest
from unittest.mock import patch
from wsgiref.simple_server import WSGIRequestHandler, make_server

from arkos_relay import agent as ag
from arkos_relay import contract as c
from arkos_relay.adapters.whatsapp import WhatsAppAdapter
from arkos_relay.api import App
from tests.relay_support import InProcessTransport, RelayFixture, wsgi


class AgentTests(RelayFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.device = self.pair(self.alice_token)
        self.videos = self.dir / "videos"
        self.videos.mkdir()
        self.agent = self.new_agent()

    def new_agent(self):
        """Simulates a PC (re)start: fresh process, same journal and outputs on disk."""
        if getattr(self, "journal", None):
            self.journal.close()
        self.transport = InProcessTransport(self.app, self.device["device_token"])
        self.journal = ag.Journal(self.dir / "journal.sqlite3")
        self.executor = ag.Executor(self.dir / "outputs", {"videos": self.videos})
        return ag.Agent(self.transport, self.device["device_id"], self.journal, self.executor, clock=self.clock)

    def tearDown(self):
        self.journal.close()
        super().tearDown()

    def approved_note(self, text="Resumen sintético del día", request_id="req-00000001"):
        task = self.create(self.alice_token, text=text, request_id=request_id)[1]["task"]
        self.assertEqual(self.approve(self.alice_token, task)[0], 200)
        return task

    def state(self, task):
        return self.store.get_task(self.alice, task["id"])

    def outputs(self):
        return sorted(p.name for p in (self.dir / "outputs").rglob("*") if p.is_file())

    def test_task_left_while_pc_off_runs_on_connect(self):
        task = self.approved_note()
        self.agent.run_once()
        final = self.state(task)
        self.assertEqual(final["state"], c.SUCCEEDED)
        note = self.dir / "outputs" / "notes" / f"{task['id']}.md"
        self.assertEqual(note.read_text(encoding="utf-8"), "Resumen sintético del día\n")
        self.assertEqual(final["result"]["output"]["sha256"], hashlib.sha256(note.read_bytes()).hexdigest())
        self.agent.run_once()
        self.assertEqual(self.outputs(), [f"{task['id']}.md"])

    def test_unapproved_task_is_not_delivered(self):
        self.create(self.alice_token)
        self.agent.run_once()
        self.assertEqual(self.outputs(), [])

    def test_offline_agent_keeps_journal_and_reports_on_reconnect(self):
        task = self.approved_note()
        self.transport.drop_response = {"/complete"}  # result reached? unknown to the agent
        with self.assertRaises(ag.TransportError):
            self.agent.run_once()
        self.transport.offline = True
        with self.assertRaises(ag.TransportError):
            self.agent.run_once()
        self.transport.offline = False
        self.agent.run_once()  # re-sends the same result: idempotent on the server
        self.assertEqual(self.state(task)["state"], c.SUCCEEDED)
        self.assertEqual(len(self.outputs()), 1)
        self.assertEqual(self.journal.pending(), [])

    def test_disconnect_long_enough_to_become_unknown_then_late_report(self):
        task = self.approved_note()
        self.transport.drop_response = {"/complete"}
        with self.assertRaises(ag.TransportError):
            self.agent.run_once()
        # The /complete request was in fact lost before arriving: emulate by resetting the server state.
        self.store.db.execute("UPDATE tasks SET state='running', result=NULL, result_sha256=NULL, lease_expires_at=? WHERE id=?",
                              (self.clock() + self.store.run_lease_seconds, task["id"]))
        self.clock.advance(self.store.run_lease_seconds + 1)
        self.assertEqual(self.state(task)["state"], c.UNKNOWN)
        self.agent.run_once()
        self.assertEqual(self.state(task)["state"], c.SUCCEEDED)
        self.assertEqual(len(self.outputs()), 1)

    def test_start_response_lost_executes_once(self):
        task = self.approved_note()
        self.transport.drop_response = {"/start"}
        with self.assertRaises(ag.TransportError):
            self.agent.run_once()
        self.assertEqual(self.outputs(), [])
        self.agent = self.new_agent()
        self.agent.run_once()
        self.assertEqual(self.state(task)["state"], c.SUCCEEDED)
        self.assertEqual(len(self.outputs()), 1)

    def test_crash_after_effect_before_report_is_verified_not_repeated(self):
        task = self.approved_note()
        with patch.object(ag.Journal, "phase", autospec=True, side_effect=self._crash_on("done_local")):
            with self.assertRaises(KeyboardInterrupt):
                self.agent.run_once()
        self.assertEqual(self.state(task)["state"], c.RUNNING)
        self.agent = self.new_agent()
        with patch.object(ag.Executor, "run", side_effect=AssertionError("must not re-execute")):
            self.agent.run_once()
        final = self.state(task)
        self.assertEqual((final["state"], final["result"]["message"]), (c.SUCCEEDED, "Verificado tras reinicio"))

    def test_crash_with_partial_output_is_reported_unknown(self):
        task = self.approved_note()
        with patch.object(ag.Journal, "phase", autospec=True, side_effect=self._crash_on("done_local")):
            with self.assertRaises(KeyboardInterrupt):
                self.agent.run_once()
        (self.dir / "outputs" / "notes" / f"{task['id']}.md").write_bytes(b"Resu")  # torn write
        self.agent = self.new_agent()
        self.agent.run_once()
        self.assertEqual(self.state(task)["state"], c.UNKNOWN)
        self.agent.run_once()  # no automatic retry
        self.assertEqual(self.state(task)["state"], c.UNKNOWN)

    def _crash_on(self, phase):
        original = ag.Journal.phase

        def side_effect(journal, task_id, new_phase, *args, **kwargs):
            if new_phase == phase:
                raise KeyboardInterrupt("power loss")
            return original(journal, task_id, new_phase, *args, **kwargs)
        return side_effect

    def test_agent_rejects_tampered_task_locally(self):
        task = self.approved_note()
        original = self.transport.__call__

        def tamper(method, path, body=None):
            payload = original(method, path, body)
            if path.endswith("/claim"):
                for item in payload["tasks"]:
                    item["params"] = {"text": "contenido inyectado"}
            return payload
        self.agent.call = tamper
        self.agent.run_once()
        final = self.state(task)
        self.assertEqual((final["state"], final["result"]["message"]), (c.FAILED, "La huella no coincide con lo aprobado"))
        self.assertEqual(self.outputs(), [])

    def test_agent_refuses_expired_approval_with_skewed_clock(self):
        task = self.approved_note()
        self.agent.clock = lambda: self.clock() + 7200  # PC clock ahead of approval expiry
        self.agent.run_once()
        self.assertEqual(self.state(task)["state"], c.FAILED)
        self.assertEqual(self.outputs(), [])

    def test_clip_outside_allowed_root_is_refused(self):
        outside = self.dir / "secret.mp4"
        outside.write_bytes(b"synthetic")
        (self.videos / "link.mp4").symlink_to(outside) if hasattr(os, "symlink") and os.name != "nt" else None
        for path in ("../secret.mp4", "link.mp4", "missing.mp4"):
            with self.subTest(path=path):
                if path == "link.mp4" and not (self.videos / "link.mp4").exists():
                    continue
                params = {"root": "videos", "path": path, "start_ms": 0, "duration_ms": 1000}
                status, body = self.create(self.alice_token, action="video.clip", params=params, request_id=f"req-{path}-clip")
                if status == 400:
                    continue  # rejected by the contract already
                self.approve(self.alice_token, body["task"])
                self.agent.run_once()
                self.assertEqual(self.state(body["task"])["state"], c.FAILED)
        self.assertEqual(self.outputs(), [])

    def test_unknown_root_on_this_pc_fails_without_effect(self):
        params = {"root": "descargas", "path": "a.mp4", "start_ms": 0, "duration_ms": 1000}
        task = self.create(self.alice_token, action="video.clip", params=params)[1]["task"]
        self.approve(self.alice_token, task)
        self.agent.run_once()
        self.assertIn("no autorizada", self.state(task)["result"]["message"])

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg not installed")
    def test_real_clip_from_allowed_root(self):
        source = self.videos / "demo.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=2", "-c:v", "mpeg4", str(source)], check=True)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        params = {"root": "videos", "path": "demo.mp4", "start_ms": 500, "duration_ms": 1000, "source_sha256": digest}
        task = self.create(self.alice_token, action="video.clip", params=params)[1]["task"]
        self.approve(self.alice_token, task)
        self.agent.run_once()
        final = self.state(task)
        self.assertEqual(final["state"], c.SUCCEEDED, final["result"])
        self.assertEqual(final["result"]["output"]["source_sha256"], digest)

    def test_document_is_never_overwritten(self):
        params = {"filename": "Plan semanal.md", "text": "# Plan\n- sintético\n"}
        first = self.create(self.alice_token, action="document.create", params=params)[1]["task"]
        self.approve(self.alice_token, first)
        self.agent.run_once()
        self.assertEqual(self.state(first)["state"], c.SUCCEEDED)
        target = self.dir / "outputs" / "documents" / f"{first['id']}-Plan semanal.md"
        self.assertEqual(target.read_text(encoding="utf-8"), params["text"])
        # A forced second execution of the same task id cannot clobber the file.
        outcome, result = self.agent.execute(first["id"], "document.create", params)
        self.assertEqual(outcome, c.UNKNOWN)
        self.assertEqual(target.read_text(encoding="utf-8"), params["text"])

    def test_revoked_device_stops_agent(self):
        self.call("POST", f"/v1/devices/{self.device['device_id']}/revoke", {}, self.alice_token)
        with self.assertRaises(ag.ApiError):
            self.agent.run_once()
        self.assertIn("revocado", self.agent.stopped)

    def test_server_restart_between_claim_and_report(self):
        task = self.approved_note()
        self.transport.drop_response = {"/complete"}
        with self.assertRaises(ag.TransportError):
            self.agent.run_once()
        self.restart_server()
        self.transport.app = self.app
        self.agent.run_once()
        self.assertEqual(self.state(task)["state"], c.SUCCEEDED)


class WhatsAppTests(RelayFixture, unittest.TestCase):
    SECRET, VERIFY = "synthetic-app-secret", "synthetic-verify"
    PHONE = "5490000000001"

    def setUp(self):
        super().setUp()
        self.wa = WhatsAppAdapter(self.store, self.SECRET, self.VERIFY)
        self.app = App(self.store, self.wa)
        self.store.bind_channel(self.alice, "whatsapp", self.PHONE)

    def send(self, text, message_id, phone=None, secret=None):
        payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"messages": [
            {"from": phone or self.PHONE, "id": message_id, "type": "text", "text": {"body": text}}]}}]}]}
        raw = json.dumps(payload).encode()
        signature = "sha256=" + hmac.new((secret or self.SECRET).encode(), raw, hashlib.sha256).hexdigest()
        return wsgi(self.app, "POST", "/v1/channels/whatsapp/webhook", raw=raw, headers={"X-Hub-Signature-256": signature})

    def replies(self):
        return [r["text"] for r in self.store.outbox("whatsapp")]

    def test_subscription_verification(self):
        ok = wsgi(self.app, "GET", f"/v1/channels/whatsapp/webhook?hub.mode=subscribe&hub.verify_token={self.VERIFY}&hub.challenge=42")
        self.assertEqual(ok, (200, "42"))
        self.assertEqual(wsgi(self.app, "GET", "/v1/channels/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=x&hub.challenge=42")[0], 403)

    def test_signature_required(self):
        self.assertEqual(self.send("nota hola", "wamid.1", secret="wrong")[0], 401)
        self.assertEqual(self.store.list_tasks(self.alice), [])

    def test_note_dedupe_and_approval_bound_to_hash(self):
        self.assertEqual(self.send("nota: comprar lúpulo sintético", "wamid.1")[1], {"handled": 1})
        self.assertEqual(self.send("nota: comprar lúpulo sintético", "wamid.1")[1], {"handled": 0})  # Meta retry
        tasks = self.store.list_tasks(self.alice)
        self.assertEqual(len(tasks), 1)
        task = tasks[0]
        self.assertEqual((task["channel"], task["state"]), ("whatsapp", c.AWAITING_APPROVAL))
        short, digest = task["id"][4:12], task["payload_sha256"][:8]
        self.send(f"aprobar {short} 00000000", "wamid.2")
        self.assertEqual(self.store.get_task(self.alice, task["id"])["state"], c.AWAITING_APPROVAL)
        self.send(f"aprobar {short} {digest}", "wamid.3")
        self.assertEqual(self.store.get_task(self.alice, task["id"])["state"], c.APPROVED)
        self.assertIn("Aprobada", self.replies()[-1])

    def test_unbound_number_and_cross_user_codes_are_ignored(self):
        self.assertEqual(self.send("nota intrusa", "wamid.9", phone="5490000000999")[1], {"handled": 0})
        bob_task = self.store.create_task(self.bob, "req-bob-0001", "note.create", {"text": "de Bob"})[0]
        self.send(f"aprobar {bob_task['id'][4:12]} {bob_task['payload_sha256'][:8]}", "wamid.10")
        self.assertEqual(self.store.get_task(self.bob, bob_task["id"])["state"], c.AWAITING_APPROVAL)


class HttpSmokeTest(RelayFixture, unittest.TestCase):
    def test_agent_over_real_http(self):
        class Quiet(WSGIRequestHandler):
            def log_message(self, *args):
                pass
        server = make_server("127.0.0.1", 0, self.app, handler_class=Quiet)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with self.assertRaises(ValueError):
                ag.HttpTransport(base, "x")  # plain HTTP refused unless explicitly local
            code = self.call("POST", "/v1/devices/pairing-codes", {"device_name": "PC HTTP"}, self.alice_token)[1]["code"]
            paired = ag.pair(base, code, allow_insecure_localhost=True)
            task = self.create(self.alice_token)[1]["task"]
            self.approve(self.alice_token, task)
            journal = ag.Journal(self.dir / "http-journal.sqlite3")
            try:
                transport = ag.HttpTransport(base, paired["device_token"], allow_insecure_localhost=True)
                ag.Agent(transport, paired["device_id"], journal, ag.Executor(self.dir / "http-out", {})).run_once()
            finally:
                journal.close()
            self.assertEqual(self.store.get_task(self.alice, task["id"])["state"], c.SUCCEEDED)
        finally:
            server.shutdown()
            server.server_close()

    def test_secret_roundtrip(self):
        path = self.dir / "device.token"
        ag.save_secret(path, "akd_synthetic")
        self.assertEqual(ag.load_secret(path), "akd_synthetic")
        if os.name == "nt":
            self.assertNotIn(b"akd_synthetic", path.read_bytes())


if __name__ == "__main__":
    unittest.main()
