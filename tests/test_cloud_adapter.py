"""Cloud adapter + gateway with a simulated transport and provider. No network, keys or paid calls."""
import json
import os
import re
import sqlite3
import subprocess
import sys
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
from arkos_cloud.ledger import SCHEMA_VERSION, Ledger, LedgerError, token_hash
from arkos_cloud.__main__ import main as cloud_cli
from arkos_pilot.chat import Conversations
from arkos_pilot.core import Queue
from arkos_pilot.providers import select_provider
from arkos_pilot.task_center import TaskCenter
from tests.cloud_support import (DISCLOSURE, HAIKU_5_5, TOKEN_A, TOKEN_B, TOKENS, InProcessTransport,
                                 SimulatedProvider, client_config, gateway_config, matching_client_config)

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL_TEXT = ('Te propongo una nota.\n```arkos-proposal\n'
                 '{"type": "note", "title": "Compras", "text": "Comprar café"}\n```')


def request(rid="cloud-req-0001", text="Hola", **extra):
    return dict(v=1, request_id=rid, messages=[dict(role="user", content=text)], **extra)


class Rig:
    def __init__(self, tmp, provider=None, fault=None, consent=True, delay=None, gateway=None, config=None):
        self.tmp = Path(tmp)
        self.provider = provider or SimulatedProvider()
        gateway = gateway or gateway_config()
        self.gateway = CloudGateway(gateway, self.tmp / "gw" / "ledger.sqlite3", self.provider, TOKENS)
        self.transport = InProcessTransport(self.gateway, fault=fault, delay=delay)
        self.config = config or matching_client_config(gateway)
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
        """Network, environment and SDK use are confined to the modules whose job they are."""
        network = ("urllib.request", "http.client", "http.server", "import socket", "import requests")
        allowed = {
            "http_transport.py": {"http.client"},            # PC -> gateway, verified TLS
            "server.py": {"http.server"},                    # gateway front
            "provider_anthropic.py": {"anthropic"},          # gateway -> provider (server only)
            "__main__.py": {"os.environ"},                   # serve: provider key, server side
        }
        for path in (ROOT / "arkos_cloud").glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for forbidden in ("os.environ", "getenv", "anthropic", *network):
                if forbidden in allowed.get(path.name, set()):
                    continue
                if forbidden == "anthropic" and path.name in ("__main__.py", "gateway.py", "server.py", "terms.py"):
                    # names only: these import provider_anthropic lazily or mention it in docs
                    self.assertNotIn("import anthropic", source, path.name)
                    continue
                self.assertNotIn(forbidden, source, f"{path.name} contiene {forbidden}")
        main = (ROOT / "arkos_cloud" / "__main__.py").read_text(encoding="utf-8")
        self.assertLessEqual(set(re.findall(r"os\.environ\.get\((\w+)", main)), {"KEY_ENV", "KEY_FILE_ENV", "TEST_BASE_URL_ENV"})
        self.assertNotIn("os.environ[", main)
        for client_side in ("adapter.py", "config.py", "consent.py", "http_transport.py"):
            source = (ROOT / "arkos_cloud" / client_side).read_text(encoding="utf-8")
            self.assertNotIn("PROVIDER_KEY", source, client_side)


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
        self.assertEqual(other.converse(request())["status"], "ok")  # B's own request, own ledger row
        self.assertEqual(len(rig.provider.calls), 2)
        rig.adapter.converse(request("cloud-req-a-only"))
        headers = {"Authorization": "Bearer " + TOKEN_B}
        status, body = rig.gateway.dispatch("POST", "/v1/conversations/cloud-req-a-only/cancel", headers, b"")
        self.assertEqual((status, body["charged_micro_usd"]), (200, 0))  # B's own tombstone only
        self.assertEqual(rig.row("cloud-req-a-only")["state"], "completed")
        self.assertEqual(rig.adapter.lookup("cloud-req-a-only")["state"], "completed")
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


class StagingReadinessRegressionTests(CloudTestCase):
    """Defects reproduced on 398fcc3 (see docs/CLOUD_STAGING_REVIEW.md) and their regressions."""

    def test_second_gateway_instance_is_refused_without_touching_in_flight_rows(self):
        hold = threading.Event()
        rig = self.rig(provider=SimulatedProvider(hold=hold))
        worker = threading.Thread(target=rig.adapter.converse, args=(request(),))
        worker.start()
        rig.provider.entered.wait(2)
        with self.assertRaises(RuntimeError):
            CloudGateway(gateway_config(), rig.tmp / "gw" / "ledger.sqlite3", SimulatedProvider())
        self.assertEqual(rig.row()["state"], "sent")
        hold.set()
        worker.join(5)
        self.assertEqual(rig.row()["state"], "completed")
        self.assertEqual(rig.spend()["reserved"], 0)
        self.assertGreater(rig.spend()["charged"], 0)

    def test_incompatible_schema_is_refused(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "ledger.sqlite3"
        db = sqlite3.connect(path)
        db.execute(f"PRAGMA user_version={SCHEMA_VERSION + 1}")
        db.close()
        with self.assertRaises(RuntimeError):
            CloudGateway(gateway_config(), path, SimulatedProvider())
        gateway = CloudGateway(gateway_config(), Path(tmp.name) / "other.sqlite3", SimulatedProvider())
        gateway.close()  # the lock of the refused instance was released; a valid one starts

    def test_restart_keeps_tokens_reservations_spend_and_idempotency(self):
        rig = self.rig(provider=SimulatedProvider(text=PROPOSAL_TEXT))
        first = rig.adapter.converse(request())
        rig.provider.behaviour = "lost"
        rig.adapter.converse(request("cloud-req-0002"))
        before = (rig.spend(), rig.spend("global"), rig.row("cloud-req-0002")["reserved"])
        rig.gateway.close()
        rig.gateway = CloudGateway(gateway_config(), rig.tmp / "gw" / "ledger.sqlite3", rig.provider)
        rig.transport.gateway = rig.gateway
        self.assertEqual((rig.spend(), rig.spend("global"), rig.row("cloud-req-0002")["reserved"]), before)
        self.assertEqual(rig.adapter.converse(request())["proposals"], first["proposals"])  # token persisted
        self.assertEqual(rig.adapter.converse(request("cloud-req-0002"))["error"]["code"], "outcome_uncertain")
        self.assertEqual(len(rig.provider.calls), 2)

    def test_revoked_token_is_blocked_without_restart(self):
        rig = self.rig()
        self.assertEqual(rig.adapter.converse(request())["status"], "ok")
        self.assertTrue(rig.gateway.ledger.revoke_token(token_hash(TOKEN_A)))
        result = rig.adapter.converse(request("cloud-req-0002"))
        self.assertEqual(result["error"]["code"], "unsafe_configuration")
        self.assertIsNone(rig.row("cloud-req-0002"))
        auth = {"Authorization": "Bearer " + TOKEN_A}
        self.assertEqual(rig.gateway.dispatch("GET", "/v1/conversations/cloud-req-0001", auth, b"")[0], 401)
        self.assertEqual(rig.gateway.dispatch("POST", "/v1/conversations/cloud-req-0001/cancel", auth, b"")[0], 401)
        self.assertEqual(len(rig.provider.calls), 1)
        other = CloudConversationProvider(rig.config, rig.consent, rig.transport, TOKEN_B)
        self.assertEqual(other.converse(request("cloud-req-0003"))["status"], "ok")

    def test_operator_cli_issues_lists_and_revokes_while_gateway_runs(self):
        rig = self.rig()
        ledger = str(rig.tmp / "gw" / "ledger.sqlite3")
        out = subprocess.run([sys.executable, "-B", "-m", "arkos_cloud", "token", "issue", "--ledger", ledger,
                              "--user", "user-c"], cwd=ROOT, capture_output=True, text=True, timeout=30)
        token = out.stdout.strip()
        self.assertTrue(token.startswith("akc_"), out.stderr)
        client = CloudConversationProvider(rig.config, rig.consent, rig.transport, token)
        self.assertEqual(client.converse(request("cloud-req-c001"))["status"], "ok")
        listing = subprocess.run([sys.executable, "-B", "-m", "arkos_cloud", "token", "list", "--ledger", ledger],
                                 cwd=ROOT, capture_output=True, text=True, timeout=30).stdout
        self.assertNotIn(token, listing)
        prefix = token_hash(token)[:8]
        self.assertIn(prefix, listing)
        done = subprocess.run([sys.executable, "-B", "-m", "arkos_cloud", "token", "revoke", "--ledger", ledger,
                               "--prefix", prefix], cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(client.converse(request("cloud-req-c002"))["error"]["code"], "unsafe_configuration")
        self.assertEqual(len(rig.provider.calls), 1)

    def test_day_change_carries_open_reservations_until_reconciled(self):
        now = [1_800_000_000.0]
        probe = self.rig()
        cost = probe.gateway.reservation(c.validate_request(request()))
        rig = self.rig(provider=SimulatedProvider("lost"), gateway=gateway_config(user_budget=cost, global_budget=cost))
        rig.gateway.clock = lambda: now[0]
        self.assertEqual(rig.adapter.converse(request("cloud-req-0001"))["error"]["code"], "outcome_uncertain")
        now[0] += 86_400
        rig.provider.behaviour = "ok"
        self.assertEqual(rig.adapter.converse(request("cloud-req-0002"))["error"]["code"], "budget_exhausted")
        self.assertEqual(len(rig.provider.calls), 1)
        rig.gateway.ledger.reconcile("user-a", "cloud-req-0001", 100)
        self.assertEqual(rig.adapter.converse(request("cloud-req-0003"))["status"], "ok")
        day1 = time.strftime("%Y-%m-%d", time.gmtime(now[0] - 86_400))
        self.assertEqual(rig.gateway.ledger.spend("user:user-a", day1), dict(reserved=0, charged=100))

    def test_call_in_flight_across_midnight_settles_on_its_own_day(self):
        now = [float(-(-1_800_000_000 // 86_400) * 86_400 - 1)]  # one second before a UTC midnight
        hold = threading.Event()
        rig = self.rig(provider=SimulatedProvider(hold=hold))
        rig.gateway.clock = lambda: now[0]
        worker = threading.Thread(target=rig.adapter.converse, args=(request(),))
        worker.start()
        rig.provider.entered.wait(2)
        day1 = rig.row()["day"]
        now[0] += 2
        day2 = utc_day(now[0])
        self.assertNotEqual(day1, day2)
        self.assertEqual(rig.gateway.ledger.open_reservations("user-a"), rig.row()["reserved"])
        hold.set()
        worker.join(5)
        self.assertEqual(rig.gateway.ledger.spend("user:user-a", day1)["reserved"], 0)
        self.assertEqual(rig.gateway.ledger.spend("user:user-a", day2), dict(reserved=0, charged=0))
        self.assertEqual(rig.gateway.ledger.open_reservations(), 0)

    def test_reservation_covers_haiku_long_context_tier(self):
        rig = self.rig(gateway=gateway_config(prices=HAIKU_5_5, user_budget=10**7, global_budget=10**7,
                                              max_input_chars=c.MAX_HISTORY_CHARS))
        worst = c.validate_request(dict(v=1, request_id="cloud-req-0001",
                                        messages=[dict(role="user", content="😀" * 8000)] * 4))
        bound = rig.gateway.input_bound(worst)
        self.assertGreater(bound, 100_000)
        billed = -(-bound * 500_000 // 1_000_000) + -(-DISCLOSURE["max_output_tokens"] * 2_500_000 // 1_000_000)
        self.assertGreaterEqual(rig.gateway.reservation(worst), billed)
        short = c.validate_request(request())
        short_billed = (-(-rig.gateway.input_bound(short) * 100_000 // 1_000_000)
                        + -(-DISCLOSURE["max_output_tokens"] * 500_000 // 1_000_000))
        self.assertGreaterEqual(rig.gateway.reservation(short), short_billed)
        rig.provider.usage = (100_001, 1000)  # actual usage over the threshold: whole request at long prices
        rig.adapter.converse(worst)
        self.assertEqual(rig.row()["charged"], -(-100_001 * 500_000 // 1_000_000) + -(-1000 * 2_500_000 // 1_000_000))

    def test_usage_above_reservation_is_charged_and_flagged(self):
        rig = self.rig(provider=SimulatedProvider(usage=(10**6, 10**4)))
        self.assertEqual(rig.adapter.converse(request())["status"], "ok")
        row = rig.row()
        self.assertEqual(row["overrun"], 1)
        self.assertEqual(row["charged"], 1_000_000 + 50_000)
        bogus = self.rig(provider=SimulatedProvider(usage=(-5, 10)))
        bogus.adapter.converse(request())
        self.assertEqual(bogus.row()["charged"], bogus.gateway.reservation(c.validate_request(request())))

    def test_retention_zero_stores_no_content_and_window_is_enforced(self):
        rig = self.rig(gateway=gateway_config(gateway_retention_hours=0), config=client_config(gateway_retention_hours=0))
        self.assertEqual(rig.adapter.converse(request())["status"], "ok")
        self.assertIsNone(rig.row()["response"])
        self.assertEqual(rig.adapter.converse(request())["error"]["code"], "duplicate_request")
        self.assertEqual(len(rig.provider.calls), 1)
        kept = self.rig()
        kept.adapter.converse(request())
        self.assertIsNotNone(kept.row()["response"])
        self.assertEqual(kept.gateway.ledger.purge_content(24 * 3600, now=time.time() + 24 * 3600 + 1), 1)
        self.assertIsNone(kept.row()["response"])

    def test_ledger_errors_never_leave_a_transaction_open(self):
        rig = self.rig()
        ledger = rig.gateway.ledger
        for call in (lambda: ledger.mark_sent("user-a", "missing-0001"),
                     lambda: ledger.settle("user-a", "missing-0001", "completed"),
                     lambda: ledger.reconcile("user-a", "missing-0001", 1)):
            with self.assertRaises(LedgerError):
                call()
        self.assertFalse(ledger.db.in_transaction)
        self.assertEqual(rig.adapter.converse(request())["status"], "ok")

    def test_timeout_and_cancel_that_overtakes_the_request(self):
        gate = threading.Event()
        rig = self.rig(delay=gate)
        with patch("arkos_cloud.adapter.time.monotonic", side_effect=[0, 0, 10_000, 10_000, 10_000]):
            result = rig.adapter.converse(request(timeout_s=10))
        self.assertEqual(result["error"]["code"], "outcome_uncertain")
        deadline = time.monotonic() + 2
        while not any(r["path"].endswith("/cancel") for r in rig.transport.requests) and time.monotonic() < deadline:
            time.sleep(0.01)
        gate.set()
        deadline = time.monotonic() + 2
        while len([r for r in rig.transport.requests if r["path"] == "/v1/conversations"]) < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.2)
        self.assertEqual(rig.row()["state"], "cancelled")
        self.assertEqual(rig.provider.calls, [])
        self.assertEqual(rig.spend(), dict(reserved=0, charged=0))

    def test_budget_holds_across_independent_connections_and_processes(self):
        rig = self.rig()
        path = rig.tmp / "gw" / "ledger.sqlite3"
        day, amount, cap = utc_day(), 100, 1000  # room for exactly 10 reservations
        ledgers = [Ledger(path) for _ in range(4)]
        for ledger in ledgers:
            self.addCleanup(ledger.close)
        wins = []

        def worker(index):
            for n in range(5):
                try:
                    ledgers[index].reserve(f"thread-{index}-{n}", f"rid-{index}-{n:04d}", "d", amount, day, cap, cap)
                    wins.append(1)
                except LedgerError as exc:
                    self.assertEqual(exc.code, "budget_exhausted")
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        script = ("import sys\nsys.path.insert(0, sys.argv[1])\nfrom arkos_cloud.ledger import Ledger, LedgerError\n"
                  "led = Ledger(sys.argv[2]); won = 0\n"
                  "for n in range(5):\n"
                  "    try:\n"
                  "        led.reserve('proc-%s-%d' % (sys.argv[3], n), 'rid-p%s-%04d' % (sys.argv[3], n), 'd', 100, sys.argv[4], 1000, 1000)\n"
                  "        won += 1\n"
                  "    except LedgerError as exc:\n"
                  "        assert exc.code == 'budget_exhausted', exc.code\n"
                  "print(won); led.close()\n")
        procs = [subprocess.Popen([sys.executable, "-B", "-c", script, str(ROOT), str(path), str(i), day],
                                  stdout=subprocess.PIPE, text=True) for i in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(30)
        proc_wins = sum(int(p.communicate(timeout=60)[0].strip()) for p in procs)
        self.assertTrue(all(p.returncode == 0 for p in procs))
        self.assertEqual(len(wins) + proc_wins, cap // amount)
        self.assertEqual(rig.gateway.ledger.spend("global", day), dict(reserved=cap, charged=0))

    def test_ledger_and_errors_do_not_expose_conversation_or_tokens(self):
        secret_text = "CONVERSACION-PRIVADA-7f3a"
        rig = self.rig(provider=SimulatedProvider(text="Respuesta RESPUESTA-PRIVADA-91c2"))
        rig.adapter.converse(request(text=secret_text))
        rig.provider.behaviour = "lost"
        lost = rig.adapter.converse(request("cloud-req-0002", text=secret_text + " otra"))
        too_long = rig.adapter.converse(request("cloud-req-0003", text=secret_text * 2000))
        rig.gateway.close()
        rig.gateway = CloudGateway(gateway_config(), rig.tmp / "gw" / "ledger.sqlite3", rig.provider)
        # Database, -wal and -shm while the gateway is running. The .lock file is held
        # (and unreadable on Windows) by the live instance; it never holds data.
        files = [p for p in (rig.tmp / "gw").glob("ledger.sqlite3*") if p.suffix != ".lock"]
        self.assertTrue(files)
        blob = b"".join(p.read_bytes() for p in files)
        self.assertNotIn(secret_text.encode(), blob)            # requests are stored as a digest only
        for token in (TOKEN_A, TOKEN_B):
            self.assertNotIn(token.encode(), blob)              # tokens as sha256 only
        self.assertIn(b"RESPUESTA-PRIVADA-91c2", blob)          # the reply, within the retention window
        for result in (lost, too_long):
            self.assertNotIn(secret_text, json.dumps(result))
        consent = (rig.tmp / "pc" / "cloud-consent.json").read_text(encoding="utf-8")
        self.assertNotIn(TOKEN_A, consent)

    def test_gateway_change_of_provider_model_or_terms_requires_new_consent(self):
        for change in (dict(provider="other-llm"), dict(model="synthetic-model-2"), dict(provider_retention_days=90),
                       dict(gateway_retention_hours=48), dict(policy_version="2026-12-01"), dict(max_output_tokens=2048),
                       dict(per_user_daily_micro_usd=50_000), dict(global_monthly_micro_usd=40_000_000),
                       dict(terms_verified=True)):
            with self.subTest(change=change):
                rig = self.rig(gateway=gateway_config(**change), config=client_config())
                self.assertEqual(rig.adapter.converse(request())["error"]["code"], "consent_required")
                self.assertEqual(rig.provider.calls, [])
                self.assertIsNone(rig.row())

    def test_cloud_package_cannot_approve_execute_or_offer_tools(self):
        import inspect
        params = list(inspect.signature(SimulatedProvider.complete).parameters)
        self.assertEqual(params, ["self", "system", "messages", "max_output_tokens", "timeout_s", "cancel_event"])
        rig = self.rig()
        rig.adapter.converse(request())
        self.assertEqual(rig.provider.calls[0]["system"], c.SYSTEM_PROMPT)
        for path in (ROOT / "arkos_cloud").glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for forbidden in ("from arkos_pilot", "import arkos_pilot", "approve(", "run_next", "subprocess", "tools=", '"tools"', "tool_choice"):
                self.assertNotIn(forbidden, source, f"{path.name}: {forbidden}")


class MonthlyBudgetTests(CloudTestCase):
    def test_monthly_cap_blocks_and_counts_open_reservations_from_earlier_months(self):
        rig = self.rig()
        ledger = rig.gateway.ledger
        ledger.reserve("u1", "rid-m-0001", "d", 600, "2026-10-01", 10**6, 10**6, 1000)
        ledger.reserve("u2", "rid-m-0002", "d", 300, "2026-10-15", 10**6, 10**6, 1000)
        with self.assertRaises(LedgerError) as caught:
            ledger.reserve("u3", "rid-m-0003", "d", 200, "2026-10-31", 10**6, 10**6, 1000)
        self.assertEqual(caught.exception.code, "budget_exhausted")
        # A new month starts fresh except for what is still open (in flight or uncertain).
        ledger.mark_sent("u1", "rid-m-0001")
        ledger.settle("u1", "rid-m-0001", "uncertain")
        ledger.mark_sent("u2", "rid-m-0002")
        ledger.settle("u2", "rid-m-0002", "completed", charged=100)
        with self.assertRaises(LedgerError):
            ledger.reserve("u3", "rid-m-0004", "d", 500, "2026-11-01", 10**6, 10**6, 1000)
        ledger.reserve("u3", "rid-m-0005", "d", 400, "2026-11-01", 10**6, 10**6, 1000)
        self.assertEqual(ledger.month_spend("2026-11-01"), dict(reserved=400, charged=0))
        self.assertEqual(ledger.month_spend("2026-10-31"), dict(reserved=600, charged=100))

    def test_gateway_applies_its_own_monthly_cap(self):
        probe = self.rig()
        cost = probe.gateway.reservation(c.validate_request(request()))
        rig = self.rig(gateway=gateway_config(user_budget=cost * 2, global_budget=cost * 2, monthly_budget=cost * 3))
        rig.gateway.clock = lambda: 1_792_500_000.0  # 2026-10-20 UTC
        self.assertEqual(utc_day(rig.gateway.clock()), "2026-10-20")
        rig.gateway.ledger.reserve("other", "seed-0001", "d", cost * 2 + 1, "2026-10-02", 10**9, 10**9)
        # Today's caps would allow it; this month's global spend would not.
        self.assertEqual(rig.adapter.converse(request("cloud-req-0001"))["error"]["code"], "budget_exhausted")
        self.assertEqual(rig.provider.calls, [])

    def test_monthly_config_is_required_and_consistent(self):
        with self.assertRaises(ConfigError):
            gateway_config(global_budget=1000, monthly_budget=999)
        data = json.loads((ROOT / "config" / "cloud-gateway.example.json").read_text(encoding="utf-8"))
        cfg = GatewayConfig.from_mapping(data)
        self.assertEqual((cfg.per_user_daily_micro_usd, cfg.global_daily_micro_usd, cfg.global_monthly_micro_usd),
                         (200_000, 1_000_000, 10_000_000))
        self.assertEqual((cfg.disclosure.model, cfg.disclosure.gateway_retention_hours), ("claude-haiku-5-5", 0))
        self.assertIs(cfg.disclosure.terms_verified, False)
        client = json.loads((ROOT / "config" / "cloud-client.example.json").read_text(encoding="utf-8"))
        self.assertEqual(client["disclosure"], data["disclosure"])  # same consent digest on both sides
        del data["disclosure"]["global_monthly_micro_usd"]
        with self.assertRaises(ConfigError):
            GatewayConfig.from_mapping(data)


if __name__ == "__main__":
    unittest.main()
