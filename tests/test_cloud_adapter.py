"""Cloud adapter + gateway with a simulated transport and provider. No network, keys or paid calls."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from arkos_hermes import contract as c
from arkos_cloud.adapter import CloudConversationProvider
from arkos_cloud.config import ClientConfig, ConfigError, GatewayConfig
from arkos_cloud.consent import CONFIRM_CHARS, ConsentStore
from arkos_cloud.gateway import CloudGateway, utc_day
from arkos_cloud.__main__ import main as cloud_cli
from arkos_pilot.chat import Conversations
from arkos_pilot.core import Queue
from arkos_pilot.providers import select_provider
from arkos_pilot.task_center import TaskCenter
from tests.cloud_support import (DISCLOSURE, TOKEN_A, TOKEN_B, TOKENS, InProcessTransport, SimulatedProvider,
                                 client_config, gateway_config)

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL_TEXT = ('Te propongo una nota.\n```arkos-proposal\n'
                 '{"type": "note", "title": "Compras", "text": "Comprar café"}\n```')


def request(rid="cloud-req-0001", text="Hola", **extra):
    return dict(v=1, request_id=rid, messages=[dict(role="user", content=text)], **extra)


class Rig:
    def __init__(self, tmp, provider=None, fault=None, consent=True, delay=None, gateway=None, config=None):
        self.tmp = Path(tmp)
        self.provider = provider or SimulatedProvider()
        self.gateway = CloudGateway(gateway or gateway_config(), self.tmp / "gw" / "ledger.sqlite3",
                                    self.provider, TOKENS)
        self.transport = InProcessTransport(self.gateway, fault=fault, delay=delay)
        self.config = config or client_config()
        self.consent = ConsentStore(self.tmp / "pc")
        if consent:
            self.consent.grant(self.config.disclosure, self.config.disclosure.digest()[:CONFIRM_CHARS])
        self.adapter = CloudConversationProvider(self.config, self.consent, self.transport, TOKEN_A)

    def row(self, rid="cloud-req-0001", user="user-a"):
        return self.gateway.ledger.get(user, rid)

    def spend(self, scope="user:user-a"):
        return self.gateway.ledger.spend(scope, utc_day())

    def close(self):
        self.gateway.close()


class CloudTestCase(unittest.TestCase):
    def rig(self, **kwargs):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        rig = Rig(tmp.name, **kwargs)
        self.addCleanup(rig.close)
        return rig


class ConfigTests(CloudTestCase):
    def base(self, **over):
        return dict(dict(gateway_url="https://gw.example", timeout_s=30, disclosure=dict(DISCLOSURE)), **over)

    def test_explicit_config_is_required_and_strict(self):
        self.assertEqual(ClientConfig.from_mapping(self.base()).gateway_url, "https://gw.example")
        bad = [self.base(extra=1), {k: v for k, v in self.base().items() if k != "timeout_s"},
               self.base(gateway_url="http://gw.example"), self.base(gateway_url="https://u:p@gw.example"),
               self.base(gateway_url="https://gw.example/?k=1"), self.base(timeout_s=5), self.base(timeout_s="30"),
               self.base(disclosure=dict(DISCLOSURE, max_input_chars=c.MAX_HISTORY_CHARS + 1)),
               self.base(disclosure=dict(DISCLOSURE, extra="x")), None, []]
        for data in bad:
            with self.subTest(data=data), self.assertRaises(ConfigError):
                ClientConfig.from_mapping(data)
        self.assertEqual(ClientConfig.from_mapping(self.base(gateway_url="http://127.0.0.1:9")).timeout_s, 30)

    def test_provider_secrets_are_refused_in_client_config(self):
        for data in [self.base(api_key="x"), self.base(provider_token="x"), self.base(anthropic_secret="x"),
                     self.base(gateway_url="https://sk-ant-api03-abcdefghijk.example"),
                     self.base(disclosure=dict(DISCLOSURE, model="sk-abcdefghijklmnop"))]:
            with self.subTest(data=list(data)), self.assertRaises(ConfigError):
                ClientConfig.from_mapping(data)

    def test_gateway_budget_relation(self):
        with self.assertRaises(ConfigError):
            gateway_config(user_budget=10, global_budget=5)

    def test_adapter_refuses_provider_key_as_token_and_hides_token(self):
        rig = self.rig()
        for token in ["sk-ant-api03-" + "x" * 40, "", None, "akc_short"]:
            with self.subTest(token=token), self.assertRaises(ValueError):
                CloudConversationProvider(rig.config, rig.consent, rig.transport, token)
        self.assertNotIn(TOKEN_A, repr(rig.adapter))

    def test_cloud_package_reads_no_environment_or_network(self):
        for path in (ROOT / "arkos_cloud").glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for forbidden in ("os.environ", "getenv", "urllib.request", "http.client", "socket", "requests", "anthropic"):
                self.assertNotIn(forbidden, source, f"{path.name} contiene {forbidden}")


class ConsentTests(CloudTestCase):
    def test_no_consent_means_nothing_is_sent(self):
        rig = self.rig(consent=False)
        result = rig.adapter.converse(request())
        self.assertEqual(result["error"]["code"], "consent_required")
        self.assertEqual((result["reply"], result["proposals"]), ("", []))
        self.assertEqual(rig.transport.requests, [])
        self.assertEqual(rig.provider.calls, [])

    def test_grant_requires_typed_code_and_binds_to_disclosure(self):
        rig = self.rig(consent=False)
        with self.assertRaises(ValueError):
            rig.consent.grant(rig.config.disclosure, "000000000000")
        rig.consent.grant(rig.config.disclosure, rig.config.disclosure.digest()[:CONFIRM_CHARS].upper())
        self.assertEqual(rig.adapter.converse(request())["status"], "ok")
        changed = client_config(model="synthetic-model-2")
        other = CloudConversationProvider(changed, rig.consent, rig.transport, TOKEN_A)
        self.assertEqual(other.converse(request("cloud-req-0002"))["error"]["code"], "consent_required")
        self.assertEqual(len(rig.provider.calls), 1)
        self.assertTrue(rig.consent.revoke())
        self.assertEqual(rig.adapter.converse(request("cloud-req-0003"))["error"]["code"], "consent_required")
        self.assertEqual(len(rig.provider.calls), 1)

    def test_gateway_enforces_consent_independently(self):
        rig = self.rig()
        body = json.dumps(request()).encode()
        headers = {"Authorization": "Bearer " + TOKEN_A, "Content-Type": "application/json",
                   "Idempotency-Key": "cloud-req-0001"}
        for consent in [None, "0" * 64, client_config(region="other").disclosure.digest()]:
            h = dict(headers, **({"X-Arkos-Consent": consent} if consent else {}))
            status, data = rig.gateway.dispatch("POST", "/v1/conversations", h, body)
            self.assertEqual((status, data["error"]["code"]), (412, "consent_required"))
        self.assertIsNone(rig.row())
        self.assertEqual(rig.provider.calls, [])

    def test_consent_cli_show_accept_revoke(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cfg = Path(tmp.name) / "cloud.json"
        cfg.write_text(json.dumps(dict(gateway_url="https://gw.example", timeout_s=30, disclosure=DISCLOSURE)))
        state = Path(tmp.name) / "state"
        code = client_config().disclosure.digest()[:CONFIRM_CHARS]
        with patch("sys.stdout"), patch("sys.stderr"):
            self.assertEqual(cloud_cli(["consent", "--config", str(cfg), "--state", str(state)]), 0)
            self.assertFalse((state / "cloud-consent.json").exists())
            self.assertEqual(cloud_cli(["consent", "--config", str(cfg), "--state", str(state), "--accept", "nope"]), 1)
            self.assertEqual(cloud_cli(["consent", "--config", str(cfg), "--state", str(state), "--accept", code]), 0)
            self.assertTrue(ConsentStore(state).valid_for(client_config().disclosure))
            self.assertEqual(cloud_cli(["consent", "--config", str(cfg), "--state", str(state), "--revoke"]), 0)
        self.assertFalse((state / "cloud-consent.json").exists())


class LimitTests(CloudTestCase):
    def test_input_limits_checked_before_sending(self):
        rig = self.rig(config=client_config(max_input_chars=100), gateway=gateway_config(max_input_chars=100))
        self.assertEqual(rig.adapter.converse(request(text="x" * 101))["error"]["code"], "invalid_request")
        too_many = dict(v=1, request_id="cloud-req-0009",
                        messages=[dict(role="user", content="a")] * (c.MAX_MESSAGES + 1))
        self.assertEqual(rig.adapter.converse(too_many)["error"]["code"], "invalid_request")
        self.assertEqual(rig.transport.requests, [])

    def test_gateway_input_limits_and_body_size(self):
        rig = self.rig(gateway=gateway_config(max_input_chars=100), config=client_config(max_input_chars=12000))
        # A client whose limits differ from the gateway's has consented to another disclosure.
        self.assertEqual(rig.adapter.converse(request(text="x" * 101))["error"]["code"], "consent_required")
        headers = {"Authorization": "Bearer " + TOKEN_A, "Content-Type": "application/json"}
        direct = dict(headers, **{"Idempotency-Key": "cloud-req-0001",
                                  "X-Arkos-Consent": rig.gateway.config.disclosure.digest()})
        status, data = rig.gateway.dispatch("POST", "/v1/conversations", direct, json.dumps(request(text="x" * 101)).encode())
        self.assertEqual((status, data["error"]["code"]), (400, "invalid_request"))
        mismatched = dict(direct, **{"Idempotency-Key": "other-key-0001"})
        self.assertEqual(rig.gateway.dispatch("POST", "/v1/conversations", mismatched, json.dumps(request()).encode())[0], 400)
        self.assertIsNone(rig.row())
        self.assertEqual(rig.gateway.dispatch("POST", "/v1/conversations", headers, b"x" * (256 * 1024 + 1))[0], 413)
        self.assertEqual(rig.gateway.dispatch("POST", "/v1/conversations", dict(headers, **{"Content-Type": "text/plain"}), b"{}")[0], 415)
        self.assertEqual(rig.provider.calls, [])

    def test_output_limits(self):
        long_reply = "r" * (c.MAX_REPLY_CHARS + 500)
        blocks = "".join('\n```arkos-proposal\n{"type": "note", "title": "N%d", "text": "t%d"}\n```' % (i, i) for i in range(5))
        rig = self.rig(provider=SimulatedProvider(text=long_reply + blocks))
        result = rig.adapter.converse(request())
        self.assertEqual(result["status"], "ok")
        self.assertLessEqual(len(result["reply"]), c.MAX_REPLY_CHARS)
        self.assertEqual(len(result["proposals"]), c.MAX_PROPOSALS)
        self.assertEqual(rig.provider.calls[0]["max_output_tokens"], DISCLOSURE["max_output_tokens"])
        huge = self.rig(provider=SimulatedProvider("huge"))
        result = huge.adapter.converse(request())
        self.assertEqual((result["error"]["code"], result["reply"]), ("output_invalid", ""))
        self.assertGreater(huge.row()["charged"], 0)  # truthful billing even when content is refused

    def test_bad_gateway_responses_are_uncertain_not_retried(self):
        for fault in ["garbage", "oversize"]:
            with self.subTest(fault=fault):
                rig = self.rig(fault=fault)
                result = rig.adapter.converse(request())
                self.assertEqual(result["error"]["code"], "outcome_uncertain")
                self.assertEqual(len(rig.transport.posts()), 1)

    def test_tampered_proposal_is_rejected(self):
        rig = self.rig(provider=SimulatedProvider(text=PROPOSAL_TEXT))
        original = rig.gateway.dispatch

        def tamper(*args):
            status, data = original(*args)
            data["proposals"][0]["text"] = "rm -rf /"
            return status, data
        rig.gateway.dispatch = tamper
        result = rig.adapter.converse(request())
        self.assertEqual((result["error"]["code"], result["proposals"]), ("outcome_uncertain", []))


class BudgetTests(CloudTestCase):
    def test_reservation_is_committed_before_the_call_and_settled_after(self):
        rig = self.rig()
        seen = {}
        rig.provider.observe = lambda: seen.update(row=rig.row(), spend=rig.spend(), global_=rig.spend("global"))
        result = rig.adapter.converse(request())
        self.assertEqual(result["status"], "ok")
        self.assertEqual(seen["row"]["state"], "sent")
        self.assertGreater(seen["row"]["reserved"], 0)
        self.assertEqual(seen["spend"]["reserved"], seen["row"]["reserved"])
        self.assertEqual(seen["global_"]["reserved"], seen["row"]["reserved"])
        expected = -(-120 * 1_000_000 // 1_000_000) + -(-40 * 5_000_000 // 1_000_000)
        self.assertEqual(rig.spend(), dict(reserved=0, charged=expected))
        self.assertEqual(rig.row()["state"], "completed")

    def test_unknown_usage_charges_the_full_reservation(self):
        rig = self.rig(provider=SimulatedProvider("no_usage"))
        rig.adapter.converse(request())
        row = rig.row()
        self.assertEqual(rig.spend()["charged"], rig.gateway.reservation(c.validate_request(request())))
        self.assertEqual(row["state"], "completed")

    def test_exhausted_budget_blocks_the_call(self):
        cost = None
        for scope, kwargs in [("user", dict(user_budget=1)), ("global", dict(user_budget=1, global_budget=1))]:
            with self.subTest(scope=scope):
                rig = self.rig(gateway=gateway_config(**kwargs))
                result = rig.adapter.converse(request())
                self.assertEqual(result["error"]["code"], "budget_exhausted")
                self.assertEqual(rig.provider.calls, [])
                self.assertIsNone(rig.row())
        rig = self.rig()
        cost = rig.gateway.reservation(c.validate_request(request()))
        tight = self.rig(gateway=gateway_config(user_budget=cost + 100))
        self.assertEqual(tight.adapter.converse(request("cloud-req-0001"))["status"], "ok")
        # Charged 320 µUSD; the next worst-case reservation no longer fits.
        self.assertEqual(tight.adapter.converse(request("cloud-req-0002"))["error"]["code"], "budget_exhausted")
        self.assertEqual(len(tight.provider.calls), 1)

    def test_global_budget_is_shared_across_users(self):
        rig = self.rig()
        cost = rig.gateway.reservation(c.validate_request(request()))
        shared = self.rig(gateway=gateway_config(user_budget=cost, global_budget=cost))
        hold = threading.Event()
        shared.provider.hold = hold
        first = threading.Thread(target=shared.adapter.converse, args=(request(),))
        first.start()
        shared.provider.entered.wait(2)
        other = CloudConversationProvider(shared.config, shared.consent, shared.transport, TOKEN_B)
        self.assertEqual(other.converse(request("cloud-req-0002"))["error"]["code"], "budget_exhausted")
        hold.set()
        first.join(5)
        self.assertEqual(len(shared.provider.calls), 1)

    def test_one_call_in_flight_per_user(self):
        hold = threading.Event()
        rig = self.rig(provider=SimulatedProvider(hold=hold))
        first = threading.Thread(target=rig.adapter.converse, args=(request(),))
        first.start()
        rig.provider.entered.wait(2)
        self.assertEqual(rig.adapter.converse(request("cloud-req-0002"))["error"]["code"], "duplicate_request")
        hold.set()
        first.join(5)
        self.assertEqual(len(rig.provider.calls), 1)


class IdempotencyTests(CloudTestCase):
    def test_same_request_is_answered_once(self):
        rig = self.rig(provider=SimulatedProvider(text=PROPOSAL_TEXT))
        first = rig.adapter.converse(request())
        second = rig.adapter.converse(request())
        self.assertEqual(first["proposals"], second["proposals"])
        self.assertEqual(len(rig.provider.calls), 1)
        self.assertEqual(rig.spend()["charged"], rig.row()["charged"])

    def test_same_id_with_other_content_conflicts(self):
        rig = self.rig()
        rig.adapter.converse(request())
        result = rig.adapter.converse(request(text="Otra cosa"))
        self.assertEqual(result["error"]["code"], "duplicate_request")
        self.assertEqual(len(rig.provider.calls), 1)

    def test_concurrent_duplicates_make_one_call(self):
        hold = threading.Event()
        rig = self.rig(provider=SimulatedProvider(hold=hold))
        results = []
        threads = [threading.Thread(target=lambda: results.append(rig.adapter.converse(request()))) for _ in range(12)]
        for t in threads:
            t.start()
        rig.provider.entered.wait(2)
        time.sleep(0.2)
        hold.set()
        for t in threads:
            t.join(5)
        self.assertEqual(len(rig.provider.calls), 1)
        self.assertEqual(sum(r["status"] == "ok" for r in results), 1)
        self.assertTrue(all(r["status"] == "ok" or r["error"]["code"] == "outcome_uncertain" for r in results))

    def test_users_are_isolated(self):
        rig = self.rig()
        rig.adapter.converse(request())
        other = CloudConversationProvider(rig.config, rig.consent, rig.transport, TOKEN_B)
        self.assertIsNone(other.lookup("cloud-req-0001"))
        headers = {"Authorization": "Bearer " + TOKEN_B}
        self.assertEqual(rig.gateway.dispatch("POST", "/v1/conversations/cloud-req-0001/cancel", headers, b"")[0], 404)
        self.assertEqual(other.converse(request())["status"], "ok")  # B's own request, own ledger row
        self.assertEqual(len(rig.provider.calls), 2)
        for auth in [{}, {"Authorization": "Bearer akc_" + "z" * 40}, {"Authorization": TOKEN_A}]:
            self.assertEqual(rig.gateway.dispatch("GET", "/v1/conversations/cloud-req-0001", auth, b"")[0], 401)


class LostResponseTests(CloudTestCase):
    def test_response_lost_after_gateway_is_uncertain_and_never_recalled(self):
        rig = self.rig(fault="drop_response", provider=SimulatedProvider(text=PROPOSAL_TEXT))
        result = rig.adapter.converse(request())
        self.assertEqual((result["error"]["code"], result["proposals"]), ("outcome_uncertain", []))
        self.assertEqual(len(rig.transport.posts()), 1)
        self.assertEqual(rig.adapter.lookup("cloud-req-0001")["state"], "completed")
        rig.transport.fault = None  # a later *human* retry with the same id replays, never re-calls
        replay = rig.adapter.converse(request())
        self.assertEqual(replay["status"], "ok")
        self.assertEqual(len(rig.provider.calls), 1)

    def test_provider_loss_keeps_reservation_and_blocks_repeat(self):
        rig = self.rig(provider=SimulatedProvider("lost"))
        result = rig.adapter.converse(request())
        self.assertEqual(result["error"]["code"], "outcome_uncertain")
        row = rig.row()
        self.assertEqual(row["state"], "uncertain")
        self.assertEqual(rig.spend()["reserved"], row["reserved"])
        self.assertEqual(rig.adapter.converse(request())["error"]["code"], "outcome_uncertain")
        self.assertEqual(len(rig.provider.calls), 1)
        reconciled = rig.gateway.ledger.reconcile("user-a", "cloud-req-0001", 250)
        self.assertEqual(reconciled["state"], "reconciled")
        self.assertEqual(rig.spend(), dict(reserved=0, charged=250))
        self.assertEqual(rig.adapter.converse(request())["error"]["code"], "outcome_uncertain")
        self.assertEqual(len(rig.provider.calls), 1)

    def test_definite_failures_release_the_reservation(self):
        for behaviour in ["not_sent", "rejected"]:
            with self.subTest(behaviour=behaviour):
                rig = self.rig(provider=SimulatedProvider(behaviour))
                self.assertEqual(rig.adapter.converse(request())["error"]["code"], "provider_unavailable")
                self.assertEqual(rig.row()["state"], "failed")
                self.assertEqual(rig.spend(), dict(reserved=0, charged=0))
                rig.adapter.converse(request())
                self.assertEqual(len(rig.provider.calls), 1)

    def test_transport_not_sent_is_definite(self):
        rig = self.rig(fault="not_sent")
        self.assertEqual(rig.adapter.converse(request())["error"]["code"], "provider_unavailable")
        self.assertIsNone(rig.row())

    def test_gateway_restart_recovers_without_resending(self):
        rig = self.rig()
        ledger = rig.gateway.ledger
        day = utc_day()
        ledger.reserve("user-a", "cloud-req-0001", "d1", 500, day, 10_000, 10_000)
        ledger.mark_sent("user-a", "cloud-req-0001")
        ledger.reserve("user-b", "cloud-req-0002", "d2", 300, day, 10_000, 10_000)
        rig.gateway.close()
        restarted = CloudGateway(gateway_config(), rig.tmp / "gw" / "ledger.sqlite3", rig.provider, TOKENS)
        self.addCleanup(restarted.close)
        self.assertEqual(restarted.ledger.get("user-a", "cloud-req-0001")["state"], "uncertain")
        self.assertEqual(restarted.ledger.get("user-b", "cloud-req-0002")["state"], "failed")
        self.assertEqual(restarted.ledger.spend("global", day), dict(reserved=500, charged=0))
        self.assertEqual(rig.provider.calls, [])
        rig.gateway = restarted

    def test_adapter_timeout_is_uncertain(self):
        gate = threading.Event()
        rig = self.rig(delay=gate, config=client_config())
        with patch("arkos_cloud.adapter.time.monotonic", side_effect=[0, 0, 10_000, 10_000, 10_000]):
            result = rig.adapter.converse(request(timeout_s=10))
        gate.set()
        self.assertEqual((result["status"], result["error"]["code"]), ("timeout", "outcome_uncertain"))
        self.assertEqual(len(rig.transport.posts()), 1)

    def test_retention_purges_content_but_keeps_billing(self):
        rig = self.rig()
        rig.adapter.converse(request())
        rig.gateway.ledger.purge_content(-1)
        self.assertIsNone(rig.row()["response"])
        self.assertGreater(rig.row()["charged"], 0)
        self.assertEqual(rig.adapter.converse(request())["error"]["code"], "duplicate_request")
        self.assertEqual(len(rig.provider.calls), 1)


class CancelTests(CloudTestCase):
    def test_cancel_during_call_discards_late_content(self):
        hold = threading.Event()
        rig = self.rig(provider=SimulatedProvider(text=PROPOSAL_TEXT, hold=hold))
        cancel, out = threading.Event(), {}
        worker = threading.Thread(target=lambda: out.update(r=rig.adapter.converse(request(), cancel)))
        worker.start()
        rig.provider.entered.wait(2)
        started = time.monotonic()
        cancel.set()
        worker.join(2)
        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual((out["r"]["status"], out["r"]["reply"], out["r"]["proposals"]), ("cancelled", "", []))
        deadline = time.monotonic() + 2
        while rig.row()["cancel_requested"] == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        hold.set()
        deadline = time.monotonic() + 2
        while rig.row()["state"] == "sent" and time.monotonic() < deadline:
            time.sleep(0.01)
        row = rig.row()
        self.assertEqual(row["state"], "cancelled")
        self.assertIsNone(row["response"])
        self.assertGreater(row["charged"], 0)  # cancelling does not pretend the provider did no work
        self.assertEqual(rig.adapter.converse(request())["status"], "cancelled")
        self.assertEqual(len(rig.provider.calls), 1)

    def test_cancel_before_send(self):
        rig = self.rig()
        cancel = threading.Event()
        cancel.set()
        self.assertEqual(rig.adapter.converse(request(), cancel)["status"], "cancelled")
        self.assertEqual(rig.transport.requests, [])

    def test_cancel_between_reservation_and_send_releases(self):
        rig = self.rig()
        ledger, day = rig.gateway.ledger, utc_day()
        ledger.reserve("user-a", "cloud-req-0001", "d", 400, day, 10_000, 10_000)
        self.assertEqual(ledger.request_cancel("user-a", "cloud-req-0001")["state"], "cancelled")
        self.assertFalse(ledger.mark_sent("user-a", "cloud-req-0001"))
        self.assertEqual(ledger.spend("user:user-a", day), dict(reserved=0, charged=0))
        self.assertEqual(rig.provider.calls, [])


class ChatIntegrationTests(CloudTestCase):
    def wait(self, chat, rid):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            turn = chat.get(rid)
            if turn["state"] != "waiting":
                return turn
            time.sleep(0.01)
        self.fail("turno sin terminar")

    def test_reuses_chat_and_queue_and_never_approves(self):
        rig = self.rig(provider=SimulatedProvider(text=PROPOSAL_TEXT))
        root = rig.tmp / "center"
        # 'synthetic' is honest here: the transport and provider are simulated. 'cloud' stays closed.
        chat = Conversations(root, rig.adapter, "synthetic")
        self.addCleanup(chat.close)
        chat.start(request())
        turn = self.wait(chat, "cloud-req-0001")
        self.assertEqual(turn["state"], "ok")
        proposal = turn["response"]["proposals"][0]
        task = chat.create_note("cloud-req-0001", proposal["proposal_id"])
        self.assertEqual((task["state"], task["approval_until"]), ("awaiting_approval", None))
        queue = Queue(root)
        self.addCleanup(queue.close)
        self.assertEqual([t["state"] for t in queue.list()], ["awaiting_approval"])
        self.assertEqual(list((root / "outputs").iterdir()), [])
        self.assertEqual(len(rig.provider.calls), 1)

    def test_chat_cancel_reaches_the_gateway(self):
        hold = threading.Event()
        rig = self.rig(provider=SimulatedProvider(text=PROPOSAL_TEXT, hold=hold))
        chat = Conversations(rig.tmp / "center", rig.adapter, "synthetic")
        self.addCleanup(chat.close)
        chat.start(request())
        rig.provider.entered.wait(2)
        self.assertEqual(chat.cancel("cloud-req-0001")["state"], "cancelled")
        deadline = time.monotonic() + 2
        while rig.row()["cancel_requested"] == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        hold.set()
        self.assertEqual(rig.row()["cancel_requested"], 1)

    def test_lost_response_in_chat_is_not_retried(self):
        rig = self.rig(provider=SimulatedProvider("lost"))
        chat = Conversations(rig.tmp / "center", rig.adapter, "synthetic")
        self.addCleanup(chat.close)
        chat.start(request())
        self.assertEqual(self.wait(chat, "cloud-req-0001")["state"], "error")
        chat.start(request())  # the UI's idempotent retry: same turn, no new call
        self.assertEqual(len(rig.provider.calls), 1)
        self.assertEqual(len(rig.transport.posts()), 1)

    def test_cloud_mode_stays_disabled(self):
        rig = self.rig()
        with self.assertRaises(ValueError):
            select_provider(rig.adapter, "cloud")
        with tempfile.TemporaryDirectory() as tmp, \
                patch("arkos_pilot.task_center.ThreadingHTTPServer.__init__") as server:
            with self.assertRaises(ValueError):
                TaskCenter(Path(tmp) / "s", bridge=rig.adapter, chat_mode="cloud")
            server.assert_not_called()
        for name in ["index.html", "chat.js", "app.js"]:
            text = (ROOT / "arkos_pilot" / "web" / name).read_text(encoding="utf-8").lower()
            self.assertNotIn("arkos_cloud", text)
            self.assertNotIn("/v1/conversations", text)
        center = (ROOT / "arkos_pilot" / "task_center.py").read_text(encoding="utf-8")
        self.assertNotIn("arkos_cloud", center)


if __name__ == "__main__":
    unittest.main()
