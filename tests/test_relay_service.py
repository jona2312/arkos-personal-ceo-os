import json
import unittest

from arkos_relay import contract as c
from tests.relay_support import RelayFixture


class ContractTests(unittest.TestCase):
    def test_digest_golden_vector(self):
        # Fixed vector for phone/WhatsApp clients implemented in other languages.
        body = c.canonical({"v": 1, "action": "note.create", "params": {"text": "Hola ñ"}, "target_device_id": None})
        self.assertEqual(body, '{"action":"note.create","params":{"text":"Hola ñ"},"target_device_id":null,"v":1}'.encode())
        self.assertEqual(c.task_digest("note.create", {"text": "Hola ñ"}, None), __import__("hashlib").sha256(body).hexdigest())

    def test_digest_binds_target_and_params(self):
        base = c.task_digest("note.create", {"text": "a"}, "dev_1")
        self.assertNotEqual(base, c.task_digest("note.create", {"text": "b"}, "dev_1"))
        self.assertNotEqual(base, c.task_digest("note.create", {"text": "a"}, "dev_2"))

    def test_allow_list_and_paths(self):
        for action, params in (("shell.run", {"command": "whoami"}), ("note.create", {"text": ""}),
                               ("note.create", {"text": "x", "extra": 1}),
                               ("document.create", {"filename": "../x.md", "text": "x"}),
                               ("document.create", {"filename": "x.exe", "text": "x"}),
                               ("video.clip", {"root": "videos", "path": "../secreto.mp4", "start_ms": 0, "duration_ms": 1}),
                               ("video.clip", {"root": "videos", "path": "C:/x.mp4", "start_ms": 0, "duration_ms": 1}),
                               ("video.clip", {"root": "videos", "path": "a.mp4", "start_ms": 0.5, "duration_ms": 1}),
                               ("video.clip", {"root": "videos", "path": "a.mp4", "start_ms": 0, "duration_ms": 0})):
            with self.assertRaises(c.ContractError, msg=(action, params)):
                c.validate_action(action, params)
        c.validate_action("video.clip", {"root": "videos", "path": "2026/a.mp4", "start_ms": 500, "duration_ms": 1000})


class ServiceTests(RelayFixture, unittest.TestCase):
    def test_authentication_required(self):
        self.assertEqual(self.call("GET", "/v1/tasks")[0], 401)
        self.assertEqual(self.call("GET", "/v1/tasks", token="aku_invalid")[0], 401)
        device = self.pair(self.alice_token)
        # A device token is not a user token, and vice versa.
        self.assertEqual(self.call("GET", "/v1/tasks", token=device["device_token"])[0], 401)
        self.assertEqual(self.call("POST", "/v1/agent/claim", {}, self.alice_token)[0], 401)

    def test_pairing_code_single_use_and_expiry(self):
        status, code = self.call("POST", "/v1/devices/pairing-codes", {"device_name": "PC"}, self.alice_token)
        self.assertEqual(self.call("POST", "/v1/pair", {"code": code["code"].lower()})[0], 201)
        self.assertEqual(self.call("POST", "/v1/pair", {"code": code["code"]})[0], 401)
        status, code = self.call("POST", "/v1/devices/pairing-codes", {"device_name": "PC"}, self.alice_token)
        self.clock.advance(601)
        self.assertEqual(self.call("POST", "/v1/pair", {"code": code["code"]})[0], 401)

    def test_pairing_brute_force_is_throttled(self):
        for _ in range(10):
            self.assertEqual(self.call("POST", "/v1/pair", {"code": "AAAA-AAAA-AAAA"})[0], 401)
        self.assertEqual(self.call("POST", "/v1/pair", {"code": "AAAA-AAAA-AAAA"})[0], 429)

    def test_task_created_while_pc_off_waits_for_approval(self):
        status, body = self.create(self.alice_token)
        self.assertEqual(status, 201)
        task = body["task"]
        self.assertEqual(task["state"], c.AWAITING_APPROVAL)
        self.assertIsNone(task["target_device_id"])
        device = self.pair(self.alice_token)
        self.assertEqual(self.call("POST", "/v1/agent/claim", {}, device["device_token"])[1]["tasks"], [])

    def test_resend_is_deduplicated_and_conflicts_detected(self):
        first = self.create(self.alice_token)
        again = self.create(self.alice_token)
        self.assertEqual((first[0], again[0]), (201, 200))
        self.assertTrue(again[1]["deduplicated"])
        self.assertEqual(first[1]["task"]["id"], again[1]["task"]["id"])
        self.assertEqual(self.create(self.alice_token, text="otra cosa")[0], 409)
        # Same client_request_id from another user is an independent task.
        self.assertEqual(self.create(self.bob_token)[0], 201)

    def test_cross_user_isolation(self):
        alice_device = self.pair(self.alice_token)
        bob_device = self.pair(self.bob_token)
        task = self.create(self.alice_token, target_device_id=alice_device["device_id"])[1]["task"]
        path = f"/v1/tasks/{task['id']}"
        self.assertEqual(self.call("GET", path, token=self.bob_token)[0], 404)
        self.assertEqual(self.approve(self.bob_token, task)[0], 404)
        self.assertEqual(self.call("POST", path + "/cancel", {}, self.bob_token)[0], 404)
        self.assertEqual(self.call("GET", "/v1/tasks", token=self.bob_token)[1]["tasks"], [])
        self.assertEqual(self.call("POST", f"/v1/devices/{alice_device['device_id']}/revoke", {}, self.bob_token)[0], 404)
        # Bob cannot target Alice's device either.
        self.assertEqual(self.create(self.bob_token, request_id="req-bob-0001", target_device_id=alice_device["device_id"])[0], 404)
        self.assertEqual(self.approve(self.alice_token, task)[0], 200)
        self.assertEqual(self.call("POST", "/v1/agent/claim", {}, bob_device["device_token"])[1]["tasks"], [])
        self.assertEqual(self.call("GET", f"/v1/agent/tasks/{task['id']}", token=bob_device["device_token"])[0], 404)
        claimed = self.call("POST", "/v1/agent/claim", {}, alice_device["device_token"])[1]["tasks"]
        self.assertEqual([t["id"] for t in claimed], [task["id"]])
        lease = claimed[0]["lease_id"]
        body = {"lease_id": lease, "payload_sha256": task["payload_sha256"]}
        self.assertEqual(self.call("POST", f"/v1/agent/tasks/{task['id']}/start", body, bob_device["device_token"])[0], 404)

    def test_approval_bound_to_exact_content(self):
        self.pair(self.alice_token)
        task = self.create(self.alice_token)[1]["task"]
        wrong = dict(task, payload_sha256=c.task_digest("note.create", {"text": "otra"}, task["target_device_id"]))
        self.assertEqual(self.approve(self.alice_token, wrong)[1]["error"]["code"], "payload_mismatch")
        self.assertEqual(self.approve(self.alice_token, task)[0], 200)
        self.assertEqual(self.approve(self.alice_token, task)[1]["error"]["code"], "invalid_state")

    def test_tampered_params_are_refused_at_start(self):
        device = self.pair(self.alice_token)
        task = self.create(self.alice_token)[1]["task"]
        self.approve(self.alice_token, task)
        claimed = self.call("POST", "/v1/agent/claim", {}, device["device_token"])[1]["tasks"][0]
        self.store.db.execute("UPDATE tasks SET params=? WHERE id=?", (json.dumps({"text": "alterado"}), task["id"]))
        status, body = self.call("POST", f"/v1/agent/tasks/{task['id']}/start",
                                 {"lease_id": claimed["lease_id"], "payload_sha256": task["payload_sha256"]}, device["device_token"])
        self.assertEqual((status, body["error"]["code"]), (409, "payload_mismatch"))

    def test_expired_approval_never_reaches_execution(self):
        device = self.pair(self.alice_token)
        task = self.create(self.alice_token)[1]["task"]
        self.approve(self.alice_token, task, ttl=60)
        self.clock.advance(61)
        self.assertEqual(self.call("POST", "/v1/agent/claim", {}, device["device_token"])[1]["tasks"], [])
        current = self.call("GET", f"/v1/tasks/{task['id']}", token=self.alice_token)[1]["task"]
        self.assertEqual((current["state"], current["state_reason"]), (c.AWAITING_APPROVAL, "approval_expired"))
        # Expiry between claim and start.
        self.approve(self.alice_token, task, ttl=100)
        claimed = self.call("POST", "/v1/agent/claim", {}, device["device_token"])[1]["tasks"][0]
        self.clock.advance(101)
        status, body = self.call("POST", f"/v1/agent/tasks/{task['id']}/start",
                                 {"lease_id": claimed["lease_id"], "payload_sha256": task["payload_sha256"]}, device["device_token"])
        self.assertEqual(status, 409)
        self.assertEqual(self.store.get_task(self.alice, task["id"])["state"], c.AWAITING_APPROVAL)

    def test_approval_ttl_bounds(self):
        task = self.create(self.alice_token)[1]["task"]
        for ttl in (0, -1, 24 * 3600 + 1, 1.5):
            self.assertEqual(self.approve(self.alice_token, task, ttl=ttl)[0], 400)

    def test_approval_is_single_use(self):
        device = self.pair(self.alice_token)
        task = self.create(self.alice_token)[1]["task"]
        self.approve(self.alice_token, task)
        claimed = self.call("POST", "/v1/agent/claim", {}, device["device_token"])[1]["tasks"][0]
        start = {"lease_id": claimed["lease_id"], "payload_sha256": task["payload_sha256"]}
        self.assertEqual(self.call("POST", f"/v1/agent/tasks/{task['id']}/start", start, device["device_token"])[0], 200)
        # Retried start on the same lease is idempotent, not a second consumption.
        self.assertEqual(self.call("POST", f"/v1/agent/tasks/{task['id']}/start", start, device["device_token"])[0], 200)
        consumed = self.store.db.execute("SELECT COUNT(*) FROM approvals WHERE task_id=? AND consumed_at IS NOT NULL", (task["id"],)).fetchone()[0]
        self.assertEqual(consumed, 1)

    def test_claim_lease_expiry_returns_task_without_effect(self):
        device = self.pair(self.alice_token)
        task = self.create(self.alice_token)[1]["task"]
        self.approve(self.alice_token, task)
        first = self.call("POST", "/v1/agent/claim", {}, device["device_token"])[1]["tasks"][0]
        self.assertEqual(self.call("POST", "/v1/agent/claim", {}, device["device_token"])[1]["tasks"], [])
        self.clock.advance(self.store.claim_lease_seconds + 1)
        second = self.call("POST", "/v1/agent/claim", {}, device["device_token"])[1]["tasks"][0]
        self.assertNotEqual(first["lease_id"], second["lease_id"])
        self.assertEqual(second["attempts"], 2)
        stale = {"lease_id": first["lease_id"], "payload_sha256": task["payload_sha256"]}
        self.assertEqual(self.call("POST", f"/v1/agent/tasks/{task['id']}/start", stale, device["device_token"])[1]["error"]["code"], "lease_lost")

    def test_running_lease_expiry_becomes_unknown_and_is_not_retried(self):
        device = self.pair(self.alice_token)
        task = self.create(self.alice_token)[1]["task"]
        self.approve(self.alice_token, task)
        claimed = self.call("POST", "/v1/agent/claim", {}, device["device_token"])[1]["tasks"][0]
        self.call("POST", f"/v1/agent/tasks/{task['id']}/start", {"lease_id": claimed["lease_id"], "payload_sha256": task["payload_sha256"]}, device["device_token"])
        self.clock.advance(self.store.run_lease_seconds + 1)
        self.assertEqual(self.call("POST", "/v1/agent/claim", {}, device["device_token"])[1]["tasks"], [])
        self.assertEqual(self.store.get_task(self.alice, task["id"])["state"], c.UNKNOWN)
        # Retry needs explicit acknowledgement and a fresh approval.
        retry_path = f"/v1/tasks/{task['id']}/retry"
        self.assertEqual(self.call("POST", retry_path, {"client_request_id": "req-retry-01"}, self.alice_token)[1]["error"]["code"], "possible_duplicate")
        status, body = self.call("POST", retry_path, {"client_request_id": "req-retry-01", "acknowledge_possible_duplicate": True}, self.alice_token)
        self.assertEqual((status, body["task"]["state"], body["task"]["retry_of"]), (201, c.AWAITING_APPROVAL, task["id"]))
        # A late, real report still settles the original.
        done = self.call("POST", f"/v1/agent/tasks/{task['id']}/complete",
                         {"lease_id": claimed["lease_id"], "outcome": "succeeded", "result": {"message": "ok"}}, device["device_token"])
        self.assertEqual(done[1]["task"]["state"], c.SUCCEEDED)

    def test_complete_is_idempotent(self):
        device = self.pair(self.alice_token)
        task = self.create(self.alice_token)[1]["task"]
        self.approve(self.alice_token, task)
        claimed = self.call("POST", "/v1/agent/claim", {}, device["device_token"])[1]["tasks"][0]
        token = device["device_token"]
        self.call("POST", f"/v1/agent/tasks/{task['id']}/start", {"lease_id": claimed["lease_id"], "payload_sha256": task["payload_sha256"]}, token)
        body = {"lease_id": claimed["lease_id"], "outcome": "succeeded", "result": {"message": "ok", "output": {"name": "a.md", "bytes": 3}}}
        self.assertEqual(self.call("POST", f"/v1/agent/tasks/{task['id']}/complete", body, token)[0], 200)
        self.assertEqual(self.call("POST", f"/v1/agent/tasks/{task['id']}/complete", body, token)[0], 200)
        body["outcome"] = "failed"
        self.assertEqual(self.call("POST", f"/v1/agent/tasks/{task['id']}/complete", body, token)[1]["error"]["code"], "already_final")
        # Results may not carry paths.
        self.assertEqual(self.call("POST", f"/v1/agent/tasks/{task['id']}/complete",
                                   {"lease_id": claimed["lease_id"], "outcome": "succeeded", "result": {"output": {"name": "C:\\x\\a.md"}}}, token)[0], 400)

    def test_cancel_after_claim_blocks_start(self):
        device = self.pair(self.alice_token)
        task = self.create(self.alice_token)[1]["task"]
        self.approve(self.alice_token, task)
        claimed = self.call("POST", "/v1/agent/claim", {}, device["device_token"])[1]["tasks"][0]
        self.assertEqual(self.call("POST", f"/v1/tasks/{task['id']}/cancel", {}, self.alice_token)[1]["task"]["state"], c.CANCELLED)
        status, _ = self.call("POST", f"/v1/agent/tasks/{task['id']}/start", {"lease_id": claimed["lease_id"], "payload_sha256": task["payload_sha256"]}, device["device_token"])
        self.assertIn(status, (404, 409))

    def test_revoked_device_loses_access_and_running_work_is_flagged(self):
        device = self.pair(self.alice_token)
        task = self.create(self.alice_token)[1]["task"]
        self.approve(self.alice_token, task)
        claimed = self.call("POST", "/v1/agent/claim", {}, device["device_token"])[1]["tasks"][0]
        self.call("POST", f"/v1/agent/tasks/{task['id']}/start", {"lease_id": claimed["lease_id"], "payload_sha256": task["payload_sha256"]}, device["device_token"])
        self.assertEqual(self.call("POST", f"/v1/devices/{device['device_id']}/revoke", {}, self.alice_token)[0], 200)
        self.assertEqual(self.call("POST", "/v1/agent/claim", {}, device["device_token"])[0], 401)
        self.assertEqual(self.store.get_task(self.alice, task["id"])["state"], c.UNKNOWN)
        # New tasks can no longer target the revoked device.
        self.assertEqual(self.create(self.alice_token, request_id="req-00000002", target_device_id=device["device_id"])[0], 404)

    def test_state_survives_server_restart(self):
        device = self.pair(self.alice_token)
        task = self.create(self.alice_token)[1]["task"]
        self.approve(self.alice_token, task)
        self.restart_server()
        claimed = self.call("POST", "/v1/agent/claim", {}, device["device_token"])[1]["tasks"]
        self.assertEqual([t["id"] for t in claimed], [task["id"]])
        self.assertEqual(self.create(self.alice_token)[0], 200)  # dedupe survives restart too

    def test_incremental_sync_by_version(self):
        first = self.create(self.alice_token)[1]["task"]
        listing = self.call("GET", "/v1/tasks?after_version=0", token=self.alice_token)[1]
        cursor = listing["next_after_version"]
        self.assertEqual(self.call("GET", f"/v1/tasks?after_version={cursor}", token=self.alice_token)[1]["tasks"], [])
        self.approve(self.alice_token, first)
        changed = self.call("GET", f"/v1/tasks?after_version={cursor}", token=self.alice_token)[1]["tasks"]
        self.assertEqual([(t["id"], t["state"]) for t in changed], [(first["id"], c.APPROVED)])

    def test_multiple_devices_require_explicit_target(self):
        self.pair(self.alice_token, "PC 1")
        self.pair(self.alice_token, "PC 2")
        self.assertEqual(self.create(self.alice_token)[1]["error"]["code"], "target_required")


if __name__ == "__main__":
    unittest.main()
