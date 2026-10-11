"""End to end over real HTTP: adapter -> HttpTransport -> GatewayServer -> CloudGateway ->
AnthropicProvider (official SDK) -> local fake Messages API. Synthetic only: no network,
keys or paid calls. Skipped when requirements-cloud.txt is not installed."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from io import StringIO
from pathlib import Path

from arkos_hermes import contract as c
from arkos_cloud.adapter import CloudConversationProvider
from arkos_cloud.config import GatewayConfig
from arkos_cloud.consent import CONFIRM_CHARS, ConsentStore
from arkos_cloud.gateway import CloudGateway, utc_day
from arkos_cloud.http_transport import HttpTransport
from arkos_cloud.ledger import Ledger
from arkos_cloud.server import GatewayServer
from arkos_pilot.chat import Conversations
from arkos_pilot.providers import select_provider
from tests.cloud_support import TOKEN_A, TOKENS, client_config
from tests.fake_anthropic import FakeAnthropic

try:
    import anthropic  # noqa: F401
    from arkos_cloud.provider_anthropic import AnthropicProvider
    HAVE_SDK = True
except ImportError:
    HAVE_SDK = False

ROOT = Path(__file__).resolve().parents[1]
FAKE_KEY = "fake-key-for-local-tests-only"
EXAMPLE = json.loads((ROOT / "config" / "cloud-gateway.example.json").read_text(encoding="utf-8"))


def pilot_gateway_config(**over):
    data = json.loads(json.dumps(EXAMPLE))
    data.update(over)
    return GatewayConfig.from_mapping(data)


def pilot_client_config():
    from arkos_cloud.config import ClientConfig
    data = json.loads((ROOT / "config" / "cloud-client.example.json").read_text(encoding="utf-8"))
    return data, ClientConfig


def request(rid="e2e-req-0001", text="Anotá comprar café", timeout_s=20):
    return dict(v=1, request_id=rid, messages=[dict(role="user", content=text)], timeout_s=timeout_s)


class LossyProxy:
    """Forwards one HTTP request to the gateway, waits for its full answer, then drops the
    client connection without relaying it: the gateway processed it, the PC never knows."""

    def __init__(self, upstream_port):
        self.upstream_port = upstream_port
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.forwarded = 0
        threading.Thread(target=self._serve, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.listener.getsockname()[1]}"

    def _serve(self):
        while True:
            try:
                client, _ = self.listener.accept()
            except OSError:
                return
            threading.Thread(target=self._relay, args=(client,), daemon=True).start()

    def _relay(self, client):
        with client:
            data = b""
            while b"\r\n\r\n" not in data:
                data += client.recv(65536)
            head, _, body = data.partition(b"\r\n\r\n")
            length = next((int(l.split(b":")[1]) for l in head.split(b"\r\n") if l.lower().startswith(b"content-length:")), 0)
            while len(body) < length:
                body += client.recv(65536)
            with socket.create_connection(("127.0.0.1", self.upstream_port)) as up:
                up.sendall(head + b"\r\n\r\n" + body)
                while up.recv(65536):
                    pass
            self.forwarded += 1

    def close(self):
        self.listener.close()


@unittest.skipUnless(HAVE_SDK, "requirements-cloud.txt no instalado")
class CloudEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.fake = FakeAnthropic()
        self.addCleanup(self.fake.close)
        self.log = StringIO()
        self.start_gateway()
        data, cls = pilot_client_config()
        self.client_config = cls.from_mapping(data)
        self.consent = ConsentStore(self.tmp / "pc")
        self.consent.grant(self.client_config.disclosure, self.client_config.disclosure.digest()[:CONFIRM_CHARS])

    def start_gateway(self, config=None):
        provider = AnthropicProvider(EXAMPLE["disclosure"]["model"], FAKE_KEY, base_url=self.fake.url)
        self.gateway = CloudGateway(config or pilot_gateway_config(), self.tmp / "gw" / "ledger.sqlite3",
                                    provider, TOKENS)
        self.server = GatewayServer(self.gateway, access_log=self.log)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.addCleanup(self.stop_gateway)

    def stop_gateway(self):
        if getattr(self, "server", None):
            self.server.shutdown()
            self.server.server_close()
            self.gateway.close()
            self.server = None

    def adapter(self, url=None):
        return CloudConversationProvider(self.client_config, self.consent, HttpTransport(url or self.server.url), TOKEN_A)

    def row(self, rid="e2e-req-0001"):
        return self.gateway.ledger.get("user-a", rid)

    def test_happy_path_reaches_chat_and_pending_task_only(self):
        chat = Conversations(self.tmp / "center", self.adapter(), "synthetic")
        self.addCleanup(chat.close)
        chat.start(request())
        deadline = time.monotonic() + 10
        while chat.get("e2e-req-0001")["state"] == "waiting" and time.monotonic() < deadline:
            time.sleep(0.02)
        turn = chat.get("e2e-req-0001")
        self.assertEqual(turn["state"], "ok", turn)
        task = chat.create_note("e2e-req-0001", turn["response"]["proposals"][0]["proposal_id"])
        self.assertEqual((task["state"], task["approval_until"]), ("awaiting_approval", None))
        sent = self.fake.requests[0]
        self.assertEqual(len(self.fake.requests), 1)
        self.assertEqual(sent["path"], "/v1/messages")
        self.assertEqual(sent["headers"]["x-api-key"], FAKE_KEY)
        body = sent["body"]
        self.assertEqual(body["model"], "claude-haiku-5-5")
        self.assertEqual(body["max_tokens"], EXAMPLE["disclosure"]["max_output_tokens"])
        self.assertEqual(body["output_config"], {"effort": "low"})
        self.assertEqual(body["system"], c.SYSTEM_PROMPT)
        for forbidden in ("tools", "tool_choice", "cache_control", "stream", "thinking", "fallbacks"):
            self.assertNotIn(forbidden, body)
        charged = self.row()["charged"]
        self.assertEqual(charged, -(-150 * 100_000 // 1_000_000) + -(-60 * 500_000 // 1_000_000))
        self.assertIsNone(self.row()["response"])  # pilot retention: 0 h

    def test_gateway_unreachable_is_definite_and_reserves_nothing(self):
        port = self.server.server_address[1]
        self.stop_gateway()
        result = self.adapter(f"http://127.0.0.1:{port}").converse(request())
        self.assertEqual(result["error"]["code"], "provider_unavailable")
        self.assertEqual(self.fake.requests, [])

    def test_provider_failures_are_single_attempts_with_correct_billing(self):
        cases = [(("status", 429), "provider_unavailable", "failed"), (("status", 400), "provider_unavailable", "failed"),
                 (("status", 500), "outcome_uncertain", "uncertain"), (("status", 529), "outcome_uncertain", "uncertain"),
                 ("drop", "outcome_uncertain", "uncertain"), ("refusal", "output_invalid", "completed")]
        for n, (action, code, state) in enumerate(cases):
            with self.subTest(action=action):
                before = len(self.fake.requests)
                self.fake.script.append(action)
                rid = f"e2e-fail-{n:04d}"
                result = self.adapter().converse(request(rid))
                self.assertEqual(result["error"]["code"], code)
                self.assertEqual(self.row(rid)["state"], state)
                self.assertEqual(len(self.fake.requests) - before, 1)  # SDK retries disabled
                if state == "uncertain":
                    self.gateway.ledger.reconcile("user-a", rid, 0)  # free the per-user slot

    def test_provider_unreachable_is_not_sent_and_released(self):
        provider = AnthropicProvider("claude-haiku-5-5", FAKE_KEY, base_url="http://127.0.0.1:9")
        self.gateway.provider = provider
        result = self.adapter().converse(request())
        self.assertEqual(result["error"]["code"], "provider_unavailable")
        self.assertEqual(self.row()["state"], "failed")
        self.assertEqual(self.gateway.ledger.open_reservations(), 0)

    def test_lost_response_with_zero_retention(self):
        proxy = LossyProxy(self.server.server_address[1])
        self.addCleanup(proxy.close)
        lossy = self.adapter(proxy.url)
        result = lossy.converse(request())
        self.assertEqual((result["error"]["code"], result["proposals"]), ("outcome_uncertain", []))
        self.assertEqual(proxy.forwarded, 1)
        direct = self.adapter()
        status = direct.lookup("e2e-req-0001")
        self.assertEqual(status["state"], "completed")
        self.assertGreater(status["charged_micro_usd"], 0)
        replay = direct.converse(request())
        # Retention 0 h: the answer was billed but not kept, so it cannot be recovered.
        self.assertEqual(replay["error"]["code"], "duplicate_request")
        self.assertEqual(len(self.fake.requests), 1)

    def test_lost_response_is_recoverable_with_retention(self):
        self.stop_gateway()
        self.start_gateway(pilot_gateway_config(disclosure=dict(EXAMPLE["disclosure"], gateway_retention_hours=1)))
        data, cls = pilot_client_config()
        data["disclosure"]["gateway_retention_hours"] = 1
        self.client_config = cls.from_mapping(data)
        self.consent.grant(self.client_config.disclosure, self.client_config.disclosure.digest()[:CONFIRM_CHARS])
        proxy = LossyProxy(self.server.server_address[1])
        self.addCleanup(proxy.close)
        self.assertEqual(self.adapter(proxy.url).converse(request())["error"]["code"], "outcome_uncertain")
        replay = self.adapter().converse(request())
        self.assertEqual(replay["status"], "ok")
        self.assertEqual(len(replay["proposals"]), 1)
        self.assertEqual(len(self.fake.requests), 1)

    def test_cancel_during_provider_call(self):
        self.fake.script.append("hold")
        cancel, out = threading.Event(), {}
        worker = threading.Thread(target=lambda: out.update(r=self.adapter().converse(request(), cancel)))
        worker.start()
        self.assertTrue(self.fake.arrived.wait(5))
        started = time.monotonic()
        cancel.set()
        worker.join(5)
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertEqual(out["r"]["status"], "cancelled")
        deadline = time.monotonic() + 5
        while self.row()["cancel_requested"] == 0 and time.monotonic() < deadline:
            time.sleep(0.02)
        self.fake.release.set()
        while self.row()["state"] == "sent" and time.monotonic() < deadline:
            time.sleep(0.02)
        row = self.row()
        self.assertEqual((row["state"], row["response"]), ("cancelled", None))
        self.assertGreater(row["charged"], 0)
        self.assertEqual(len(self.fake.requests), 1)

    def test_monthly_cap_is_enforced_by_the_gateway(self):
        ledger, day = self.gateway.ledger, utc_day()
        first_day = day[:8] + "01"
        # Pilot cap: USD 10 per month. Seed USD 9.9995 of earlier spend this month.
        ledger.reserve("operator", "seed-0001", "d", 9_999_500, first_day, 10**9, 10**9)
        self.assertEqual(self.adapter().converse(request())["error"]["code"], "budget_exhausted")
        self.assertEqual(self.fake.requests, [])

    def test_access_log_has_no_tokens_ids_or_content(self):
        self.adapter().converse(request(text="TEXTO-PRIVADO-e2e"))
        self.adapter().lookup("e2e-req-0001")
        log = self.log.getvalue()
        self.assertIn("POST /v1/conversations 200", log)
        self.assertIn("GET /v1/conversations/<id> 200", log)
        for secret in (TOKEN_A, "TEXTO-PRIVADO-e2e", "e2e-req-0001", FAKE_KEY):
            self.assertNotIn(secret, log)

    def test_server_limits_and_rate_limit(self):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        conn.putrequest("POST", "/v1/conversations")
        conn.putheader("Transfer-Encoding", "chunked")
        conn.endheaders()
        self.assertEqual(conn.getresponse().status, 411)
        conn.close()
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        conn.request("POST", "/v1/conversations", body=b"x" * (256 * 1024 + 1),
                     headers={"Content-Type": "application/json"})
        self.assertEqual(conn.getresponse().status, 413)
        conn.close()
        self.server.limiter.limit = 3
        statuses = []
        for _ in range(5):
            conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
            conn.request("GET", "/v1/conversations/e2e-req-0001")
            statuses.append(conn.getresponse().status)
            conn.close()
        self.assertEqual(statuses[-1], 429)
        self.assertNotIn(200, statuses)  # unauthenticated: 401 until the limit, then 429

    def test_cloud_stays_disabled_by_default(self):
        with self.assertRaises(ValueError):
            select_provider(self.adapter(), "cloud")
        with self.assertRaises(ValueError):
            GatewayServer(self.gateway, host="0.0.0.0")  # public bind without TLS


@unittest.skipUnless(HAVE_SDK, "requirements-cloud.txt no instalado")
class GatewayProcessRestartTests(unittest.TestCase):
    """Real process: kill -9 during a provider call, restart, and prove there is no second call."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.fake = FakeAnthropic()
        self.addCleanup(self.fake.close)
        self.ledger_path = self.tmp / "gw" / "ledger.sqlite3"
        ledger = Ledger(self.ledger_path)
        for digest, user in TOKENS.items():
            ledger.register_token_hash(digest, user)
        ledger.close()
        self.config_path = self.tmp / "gateway.json"
        self.config_path.write_text(json.dumps(EXAMPLE), encoding="utf-8")
        data, cls = pilot_client_config()
        self.client_config = cls.from_mapping(data)
        self.consent = ConsentStore(self.tmp / "pc")
        self.consent.grant(self.client_config.disclosure, self.client_config.disclosure.digest()[:CONFIRM_CHARS])

    def spawn(self):
        env = dict(os.environ, ARKOS_CLOUD_PROVIDER_KEY=FAKE_KEY, ARKOS_CLOUD_TEST_PROVIDER_URL=self.fake.url,
                   PYTHONIOENCODING="utf-8")
        proc = subprocess.Popen([sys.executable, "-B", "-m", "arkos_cloud", "serve", "--gateway-config",
                                 str(self.config_path), "--ledger", str(self.ledger_path), "--port", "0"],
                                cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            proc.stdout.close()
            proc.stderr.close()
        self.addCleanup(cleanup)
        line = proc.stdout.readline()
        if not line:
            return proc, None
        return proc, json.loads(line)["listening"]

    def test_kill_during_call_restart_and_no_second_call(self):
        proc, url = self.spawn()
        self.assertTrue(url, proc.stderr.read() if proc.poll() is not None else "")
        second, second_url = self.spawn()
        self.assertIsNone(second_url)  # a second instance on the same ledger refuses to start
        self.assertEqual(second.wait(10), 3)
        self.fake.script.append("hold")
        adapter = CloudConversationProvider(self.client_config, self.consent, HttpTransport(url), TOKEN_A)
        out = {}
        worker = threading.Thread(target=lambda: out.update(r=adapter.converse(request())))
        worker.start()
        self.assertTrue(self.fake.arrived.wait(10))
        proc.kill()  # crash while the provider call is in flight
        proc.wait(10)
        worker.join(10)
        self.assertEqual(out["r"]["error"]["code"], "outcome_uncertain")
        self.fake.release.set()
        restarted, url2 = self.spawn()
        self.assertTrue(url2)
        adapter2 = CloudConversationProvider(self.client_config, self.consent, HttpTransport(url2), TOKEN_A)
        self.assertEqual(adapter2.lookup("e2e-req-0001")["state"], "uncertain")
        self.assertEqual(adapter2.converse(request())["error"]["code"], "outcome_uncertain")
        self.assertEqual(len(self.fake.requests), 1)
        stderr_tail = ""
        restarted.terminate()
        try:
            restarted.wait(10)
        except subprocess.TimeoutExpired:
            restarted.kill()
        stderr_tail = restarted.stderr.read()
        for secret in (TOKEN_A, FAKE_KEY, "Anotá comprar café"):
            self.assertNotIn(secret, stderr_tail)
        out = subprocess.run([sys.executable, "-B", "-m", "arkos_cloud", "reconcile", "--ledger", str(self.ledger_path),
                              "--user", "user-a", "--request-id", "e2e-req-0001", "--charged", "1100"],
                             cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        ledger = Ledger(self.ledger_path)
        self.addCleanup(ledger.close)
        self.assertEqual(ledger.get("user-a", "e2e-req-0001")["state"], "reconciled")
        self.assertEqual(ledger.open_reservations(), 0)


class HttpWithoutSdkTests(unittest.TestCase):
    """Server + HTTP transport with the in-process simulated provider: runs even without the SDK."""

    def setUp(self):
        from tests.cloud_support import SimulatedProvider, gateway_config
        self.tmp = Path(tempfile.mkdtemp())
        self.provider = SimulatedProvider()
        self.gateway = CloudGateway(gateway_config(), self.tmp / "gw" / "ledger.sqlite3", self.provider, TOKENS)
        self.server = None
        self.config = client_config()
        self.consent = ConsentStore(self.tmp / "pc")
        self.consent.grant(self.config.disclosure, self.config.disclosure.digest()[:CONFIRM_CHARS])

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        self.gateway.close()

    def serve(self, **kwargs):
        self.server = GatewayServer(self.gateway, access_log=None, **kwargs)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        return self.server.url

    def test_round_trip_cancel_and_lookup_over_http(self):
        url = self.serve()
        adapter = CloudConversationProvider(self.config, self.consent, HttpTransport(url), TOKEN_A)
        self.assertEqual(adapter.converse(request(timeout_s=10))["status"], "ok")
        self.assertEqual(adapter.lookup("e2e-req-0001")["state"], "completed")
        hold = threading.Event()
        self.provider.hold = hold
        self.provider.entered.clear()
        cancel, out = threading.Event(), {}
        worker = threading.Thread(target=lambda: out.update(r=adapter.converse(request("e2e-req-0002", timeout_s=10), cancel)))
        worker.start()
        self.assertTrue(self.provider.entered.wait(5))
        cancel.set()
        worker.join(5)
        self.assertEqual(out["r"]["status"], "cancelled")
        deadline = time.monotonic() + 5
        while self.gateway.ledger.get("user-a", "e2e-req-0002")["cancel_requested"] == 0 and time.monotonic() < deadline:
            time.sleep(0.02)
        hold.set()
        while self.gateway.ledger.get("user-a", "e2e-req-0002")["state"] == "sent" and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(self.gateway.ledger.get("user-a", "e2e-req-0002")["state"], "cancelled")
        self.assertEqual(len(self.provider.calls), 2)

    def test_tls_verification(self):
        import shutil
        if not shutil.which("openssl"):
            self.skipTest("openssl no disponible")
        cert, key = self.tmp / "cert.pem", self.tmp / "key.pem"
        made = subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                               "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
                               "-keyout", str(key), "-out", str(cert)], capture_output=True, timeout=60)
        if made.returncode != 0:
            self.skipTest("openssl no pudo generar el certificado")
        url = self.serve(tls_cert=str(cert), tls_key=str(key))
        self.assertTrue(url.startswith("https://"))
        trusted = CloudConversationProvider(self.config, self.consent, HttpTransport(url, ca_file=str(cert)), TOKEN_A)
        self.assertEqual(trusted.converse(request(timeout_s=10))["status"], "ok")
        untrusted = CloudConversationProvider(self.config, self.consent, HttpTransport(url), TOKEN_A)
        result = untrusted.converse(request("e2e-req-0002", timeout_s=10))
        self.assertEqual(result["error"]["code"], "provider_unavailable")  # verification failed: nothing sent
        self.assertIsNone(self.gateway.ledger.get("user-a", "e2e-req-0002"))
        self.assertEqual(len(self.provider.calls), 1)


if __name__ == "__main__":
    unittest.main()
