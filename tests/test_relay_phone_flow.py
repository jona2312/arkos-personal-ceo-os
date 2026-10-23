"""Phone -> relay queue -> PC agent -> result on the phone, over real HTTP. Synthetic data only.

The phone side uses exactly the endpoints the web client in arkos_relay/phone calls; the
browser rendering is covered by scripts/Test-ArkosPhone.cjs.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from urllib import error, request
from wsgiref.simple_server import WSGIRequestHandler, make_server

from arkos_relay import agent as ag
from arkos_relay import contract as c
from arkos_relay.api import App
from arkos_relay.store import PRESENCE_SECONDS, Store
from tests.relay_support import Clock

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "arkos_relay" / "phone" / "app.js"


class Quiet(WSGIRequestHandler):
    def log_message(self, *args):
        pass


class Crash(BaseException):
    """The agent process dies (power cut, kill) in the middle of an effect."""


class CountingExecutor(ag.Executor):
    def __init__(self, output_dir, crash_after_partial_write=False):
        super().__init__(output_dir, {})
        self.runs = []
        self.crash_after_partial_write = crash_after_partial_write

    def run(self, task_id, action, params):
        self.runs.append(task_id)
        if self.crash_after_partial_write:
            target = self.target(task_id, action, params)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.expected_bytes(action, params)[:3])
            raise Crash()
        return super().run(task_id, action, params)


class FlakyTransport:
    """Real HTTP to the relay, with the network cut or a response lost on demand."""

    def __init__(self, inner):
        self.inner = inner
        self.offline = False
        self.lose_response_of = set()

    def __call__(self, method, path, body=None):
        if self.offline:
            raise ag.TransportError("sin red (sintético)")
        result = self.inner(method, path, body)
        for suffix in list(self.lose_response_of):
            if path.endswith(suffix):
                self.lose_response_of.discard(suffix)
                raise ag.TransportError("respuesta perdida (sintético)")
        return result


class Phone:
    """Plain HTTP client with the user token, like the web client."""

    def __init__(self, base, token):
        self.base, self.token = base, token

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = request.Request(self.base + path, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self.token)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with request.urlopen(req, timeout=10) as response:
                return response.status, json.loads(response.read())
        except error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def note(self, text, request_id):
        return self.call("POST", "/v1/tasks", {"client_request_id": request_id, "action": "note.create", "params": {"text": text}})

    def approve(self, task, ttl=8 * 3600):
        # The client recomputes the digest from what it shows; it never echoes the server's value blindly.
        digest = c.task_digest(task["action"], task["params"], task["target_device_id"])
        return self.call("POST", f"/v1/tasks/{task['id']}/approve", {"payload_sha256": digest, "ttl_seconds": ttl})

    def task(self, task_id):
        return self.call("GET", f"/v1/tasks/{task_id}")[1]["task"]

    def presence(self):
        return [d["presence"] for d in self.call("GET", "/v1/devices")[1]["devices"]]


class PhoneFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.clock = Clock()
        self.start_server()
        user = self.store.create_user("Jona Sintético")
        self.phone = Phone(self.base, self.store.issue_user_token(user))
        code = self.phone.call("POST", "/v1/devices/pairing-codes", {"device_name": "PC sintética"})[1]["code"]
        self.device = ag.pair(self.base, code, allow_insecure_localhost=True)
        self.executor = CountingExecutor(self.dir / "out")
        self.journal = None

    def tearDown(self):
        if self.journal:
            self.journal.close()
        self.stop_server()
        self.temp.cleanup()

    def start_server(self, port=0):
        self.store = Store(self.dir / "relay.sqlite3", clock=self.clock)
        self.server = make_server("127.0.0.1", port, App(self.store), handler_class=Quiet)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.store.close()

    def pc(self, executor=None):
        """Start (or restart) the agent process: same journal file, fresh objects."""
        if self.journal:
            self.journal.close()
        self.journal = ag.Journal(self.dir / "journal.sqlite3")
        self.transport = FlakyTransport(ag.HttpTransport(self.base, self.device["device_token"], allow_insecure_localhost=True))
        return ag.Agent(self.transport, self.device["device_id"], self.journal, executor or self.executor, clock=self.clock)

    def output(self, task_id):
        return self.dir / "out" / "notes" / f"{task_id}.md"

    def test_task_left_with_pc_off_runs_on_reconnect_and_result_reaches_phone(self):
        self.assertEqual(self.phone.presence(), ["never_seen"])
        status, body = self.phone.note("Llamar al contador el lunes", "phone-0001")
        self.assertEqual(status, 201)
        task = body["task"]
        self.assertEqual(self.phone.approve(task)[0], 200)
        self.clock.advance(3600)  # PC still off: nothing moves, the approval is still valid
        waiting = self.phone.task(task["id"])
        self.assertEqual(waiting["state"], c.APPROVED)
        self.assertEqual(waiting["approval_expires_at"], self.clock() - 3600 + 8 * 3600)
        self.assertEqual(self.executor.runs, [])

        self.pc().run_once()  # PC turns on and syncs (outbound only)

        done = self.phone.task(task["id"])
        self.assertEqual(done["state"], c.SUCCEEDED)
        self.assertEqual(self.phone.presence(), ["online"])
        data = self.output(task["id"]).read_bytes()
        self.assertEqual(done["result"]["output"], {"name": f"{task['id']}.md", "sha256": ag.sha256_bytes(data), "bytes": len(data)})
        self.assertEqual([e["to_state"] for e in done["events"]],
                         [c.AWAITING_APPROVAL, c.APPROVED, c.CLAIMED, c.RUNNING, c.SUCCEEDED])
        self.clock.advance(PRESENCE_SECONDS + 1)
        self.assertEqual(self.phone.presence(), ["offline"])
        self.pc().run_once()
        self.assertEqual(self.executor.runs, [task["id"]])

    def test_phone_resend_after_lost_response_does_not_duplicate(self):
        first = self.phone.note("Comprar regalo sintético", "phone-0002")
        again = self.phone.note("Comprar regalo sintético", "phone-0002")
        self.assertEqual((first[0], again[0], again[1]["deduplicated"]), (201, 200, True))
        self.assertEqual(again[1]["task"]["id"], first[1]["task"]["id"])
        clash = self.phone.note("Otro texto", "phone-0002")
        self.assertEqual((clash[0], clash[1]["error"]["code"]), (409, "idempotency_conflict"))

    def test_disconnect_during_report_then_reconnect(self):
        task = self.phone.note("Nota con corte de red", "phone-0003")[1]["task"]
        self.phone.approve(task)
        agent = self.pc()
        self.transport.lose_response_of.add("/complete")
        with self.assertRaises(ag.TransportError):
            agent.run_once()  # effect done; the relay got the report but the PC never saw the answer
        self.assertEqual(self.phone.task(task["id"])["state"], c.SUCCEEDED)
        self.transport.offline = True
        with self.assertRaises(ag.TransportError):
            agent.run_once()  # network down: journal kept, nothing executed
        self.transport.offline = False
        self.pc().run_once()  # reconnection after restart: same report re-sent (idempotent)
        self.assertEqual(self.executor.runs, [task["id"]])
        self.assertEqual(self.phone.task(task["id"])["state"], c.SUCCEEDED)

    def test_relay_restart_while_pc_offline(self):
        task = self.phone.note("Sobrevive al reinicio del relay", "phone-0004")[1]["task"]
        self.phone.approve(task)
        port = self.server.server_port
        self.stop_server()
        self.start_server(port)
        self.pc().run_once()
        self.assertEqual(self.phone.task(task["id"])["state"], c.SUCCEEDED)

    def test_approval_expired_while_pc_off_is_never_executed(self):
        task = self.phone.note("Aprobación corta", "phone-0005")[1]["task"]
        self.phone.approve(task, ttl=3600)
        self.clock.advance(3601)
        self.pc().run_once()
        self.assertEqual(self.executor.runs, [])
        expired = self.phone.task(task["id"])
        self.assertEqual((expired["state"], expired["state_reason"], expired["approval_expires_at"]),
                         (c.AWAITING_APPROVAL, "approval_expired", None))
        self.assertFalse(self.output(task["id"]).exists())
        self.assertEqual(self.phone.approve(expired)[0], 200)  # the phone re-approves the same content
        self.pc().run_once()
        self.assertEqual(self.executor.runs, [task["id"]])

    def test_approval_expiring_between_claim_and_start_is_refused(self):
        task = self.phone.note("Vence durante la reserva", "phone-0006")[1]["task"]
        self.phone.approve(task, ttl=60)
        agent = self.pc()
        claimed = self.transport("POST", "/v1/agent/claim", {"max_tasks": 1})["tasks"]
        self.clock.advance(61)
        self.assertEqual(self.phone.task(task["id"])["state"], c.AWAITING_APPROVAL)  # claimed, not started: released at once
        agent.process(claimed[0])  # local check sees the approval expired: no start, no report, no effect
        status = self.phone.task(task["id"])
        self.assertEqual((status["state"], status["state_reason"], status["result"]), (c.AWAITING_APPROVAL, "approval_expired", None))
        self.assertFalse(self.output(task["id"]).exists())
        self.assertEqual(self.phone.approve(status)[0], 200)  # same as the server-gate path: approve again
        self.pc().run_once()
        self.assertEqual(self.executor.runs, [task["id"]])

    def test_server_gate_and_agent_gate_agree(self):
        """Contract §2: whichever side notices the expiry, the task ends in awaiting_approval without effect."""
        task = self.phone.note("Vence justo antes del inicio", "phone-0010")[1]["task"]
        self.phone.approve(task, ttl=60)
        self.pc()
        claimed = self.transport("POST", "/v1/agent/claim", {"max_tasks": 1})["tasks"][0]
        self.clock.advance(61)
        body = {"lease_id": claimed["lease_id"], "payload_sha256": task["payload_sha256"]}
        with self.assertRaises(ag.ApiError) as refused:
            self.transport("POST", f"/v1/agent/tasks/{task['id']}/start", body)
        self.assertEqual((refused.exception.status, refused.exception.code), (409, "approval_expired"))
        status = self.phone.task(task["id"])
        self.assertEqual((status["state"], status["state_reason"]), (c.AWAITING_APPROVAL, "approval_expired"))
        self.assertEqual(self.executor.runs, [])

    def test_uncertain_result_is_shown_and_never_repeated(self):
        task = self.phone.note("Efecto incierto", "phone-0007")[1]["task"]
        self.phone.approve(task)
        with self.assertRaises(Crash):
            self.pc(CountingExecutor(self.dir / "out", crash_after_partial_write=True)).run_once()
        self.assertEqual(self.phone.task(task["id"])["state"], c.RUNNING)
        self.clock.advance(901)  # run lease expires while the PC is dead
        self.assertEqual(self.phone.task(task["id"])["state"], c.UNKNOWN)

        self.pc().run_once()  # PC back: verifies the partial file, reports unknown, does not re-run
        self.pc().run_once()
        self.assertEqual(self.executor.runs, [])
        uncertain = self.phone.task(task["id"])
        self.assertEqual(uncertain["state"], c.UNKNOWN)
        self.assertIn("revisar la PC", uncertain["result"]["message"])

        refused = self.phone.call("POST", f"/v1/tasks/{task['id']}/retry", {"client_request_id": "phone-0008"})
        self.assertEqual((refused[0], refused[1]["error"]["code"]), (409, "possible_duplicate"))
        retry = self.phone.call("POST", f"/v1/tasks/{task['id']}/retry",
                                {"client_request_id": "phone-0008", "acknowledge_possible_duplicate": True})[1]["task"]
        self.assertEqual(retry["state"], c.AWAITING_APPROVAL)
        self.pc().run_once()
        self.assertEqual(self.executor.runs, [])  # a retry still needs its own approval
        resolved = self.phone.call("POST", f"/v1/tasks/{task['id']}/resolve", {"outcome": "failed", "note": "no_estaba_en_pc"})
        self.assertEqual(resolved[1]["task"]["state"], c.FAILED)
        self.phone.approve(retry)
        self.pc().run_once()
        self.assertEqual(self.executor.runs, [retry["id"]])

    def test_uncertain_result_never_reveals_local_paths(self):
        task = self.phone.note("Disco con problemas", "phone-0009")[1]["task"]
        self.phone.approve(task)
        (self.dir / "out").mkdir()
        (self.dir / "out" / "notes").write_text("no es una carpeta")  # synthetic disk fault after start
        self.pc().run_once()
        uncertain = self.phone.task(task["id"])
        self.assertEqual(uncertain["state"], c.UNKNOWN)
        self.assertNotIn(str(self.dir), json.dumps(uncertain, ensure_ascii=False))
        self.assertEqual(uncertain["result"]["message"], "Resultado incierto: FileExistsError (errno 17)")

    def test_path_redaction(self):
        cases = {
            "[Errno 17] File exists: '/home/jona/agent/outputs/notes'": "[Errno 17] File exists: '<ruta local>'",
            "[WinError 5] Acceso denegado: 'C:\\Users\\Jona\\x.md'": "[WinError 5] Acceso denegado: '<ruta local>'",
            "\\\\nas\\videos\\a.mp4 no responde": "<ruta local> no responde",
            "relativo a/b.mp4, fecha 12/10, https://relay.example/v1": "relativo a/b.mp4, fecha 12/10, https://relay.example/v1",
        }
        for raw, expected in cases.items():
            self.assertEqual(ag.redact_paths(raw), expected)

    def test_presence_and_result_queries_never_claim_or_execute(self):
        task = self.phone.note("Solo consultar", "phone-0011")[1]["task"]
        self.phone.approve(task)
        code = self.phone.call("POST", f"/v1/devices/{self.device['device_id']}/viewer-codes")[1]["code"]
        viewer = ag.HttpTransport(self.base, "", allow_insecure_localhost=True).post_public("/v1/viewer/pair", {"code": code})
        reader = ag.HttpTransport(self.base, viewer["viewer_token"], allow_insecure_localhost=True)
        before = self.phone.task(task["id"])
        for _ in range(5):
            self.phone.call("GET", "/v1/devices")
            self.phone.call("GET", "/v1/tasks?after_version=0")
            self.phone.call("GET", f"/v1/tasks/{task['id']}")
            reader("GET", "/v1/viewer/tasks?after_version=0")
            request.urlopen(self.base + "/m/").read()
            self.clock.advance(30)
        after = self.phone.task(task["id"])
        self.assertEqual((after["state"], after["lease_id"], after["attempts"], after["version"]),
                         (c.APPROVED, None, 0, before["version"]))
        self.assertEqual(self.phone.presence(), ["never_seen"])  # reads by the phone or the screen do not fake an online PC
        self.assertEqual(self.executor.runs, [])

    def test_phone_page_is_served_with_strict_headers(self):
        with request.urlopen(self.base + "/m/") as response:
            html = response.read().decode()
            headers = response.headers
        self.assertIn('<script src="/m/app.js" defer></script>', html)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["Referrer-Policy"], "no-referrer")
        with request.urlopen(self.base + "/m/app.js") as response:
            self.assertTrue(response.headers["Content-Type"].startswith("text/javascript"))
            code = response.read()
            for sink in (b".innerHTML", b"insertAdjacentHTML", b"eval(", b"new Function"):
                self.assertNotIn(sink, code)
        for path in ("/m/../store.py", "/m/index.html", "/m/x.js"):
            with self.assertRaises(error.HTTPError) as caught:
                request.urlopen(self.base + path)
            self.assertEqual(caught.exception.code, 404)


@unittest.skipUnless(shutil.which("node"), "node no disponible")
class PhoneClientContractTests(unittest.TestCase):
    def node(self, script, payload):
        run = subprocess.run(["node", "-e", f"const m=require({json.dumps(str(APP_JS))});" + script],
                             input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)

    def test_js_digest_matches_python(self):
        vectors = [
            {"action": "note.create", "params": {"text": "Hola ñ"}, "target_device_id": None},
            {"action": "note.create", "params": {"text": "comillas \" barra \\ salto\nretorno\r tab\t ctrl\u0001 del\u007f"},
             "target_device_id": "dev_" + "a" * 32},
            {"action": "note.create", "params": {"text": "emoji 😀 y   separador"}, "target_device_id": None},
            {"action": "document.create", "params": {"filename": "plan.md", "text": "# Plan\n- uno"}, "target_device_id": None},
            {"action": "video.clip", "params": {"root": "videos", "path": "a/b.mp4", "start_ms": 0, "duration_ms": 90061},
             "target_device_id": "dev_" + "b" * 32},
        ]
        js = self.node("let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{const v=JSON.parse(s);"
                       "console.log(JSON.stringify(v.map(t=>m.digestBody(t))))})", vectors)
        for vector, body in zip(vectors, js):
            expected = c.canonical({"v": c.CONTRACT_VERSION, **vector})
            self.assertEqual(body.encode("utf-8"), expected)
            self.assertEqual(c.task_digest(vector["action"], vector["params"], vector["target_device_id"]),
                             __import__("hashlib").sha256(body.encode("utf-8")).hexdigest())

    def test_js_refuses_floats_like_python(self):
        run = subprocess.run(["node", "-e", f"require({json.dumps(str(APP_JS))}).canonical({{a:1.5}})"],
                             capture_output=True, text=True, timeout=30)
        self.assertNotEqual(run.returncode, 0)

    def test_state_guidance(self):
        online = {"presence": "online", "name": "PC"}
        offline = {"presence": "offline", "name": "PC"}
        cases = [
            ({"state": "awaiting_approval", "state_reason": "approval_expired"}, None),
            ({"state": "approved", "approval_expires_at": None}, offline),
            ({"state": "approved", "approval_expires_at": None}, online),
            ({"state": "running"}, online),
            ({"state": "unknown"}, offline),
            ({"state": "succeeded", "state_reason": "Archivo creado"}, online),
            ({"state": "succeeded", "state_reason": "confirmado_en_pc"}, online),
        ]
        out = self.node("let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{const v=JSON.parse(s);"
                        "console.log(JSON.stringify(v.map(([t,d])=>m.describe(t,d))))})", cases)
        expired, waiting_off, waiting_on, running, unknown, done, resolved = out
        self.assertIn("venció", expired["hint"])
        self.assertIn("No se ejecutó nada", expired["hint"])
        self.assertEqual(expired["actions"], ["review", "reject", "cancel"])
        self.assertIn("no está conectada", waiting_off["hint"])
        self.assertIn("está conectada", waiting_on["hint"])
        self.assertEqual(running["actions"], [])
        self.assertEqual((unknown["tone"], unknown["actions"]), ("warn", ["resolve", "retry"]))
        self.assertIn("No se repite sola", unknown["hint"])
        self.assertEqual(done["hint"], "La PC confirmó el resultado.")
        self.assertIn("por vos", resolved["hint"])


if __name__ == "__main__":
    unittest.main()
