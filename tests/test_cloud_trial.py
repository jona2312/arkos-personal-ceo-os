"""Cumulative trial budget (USD 1 in the pilot) and per-turn latency. Fake provider only."""
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from arkos_hermes import contract as c
from arkos_cloud.__main__ import _open_trial, _percentile
from arkos_cloud.gateway import CloudGateway, utc_day
from arkos_cloud.ledger import SCHEMA_VERSION, Ledger, LedgerError
from tests.cloud_support import SimulatedProvider, TOKENS, gateway_config
from tests.test_cloud_adapter import Rig, request

DAY = 86_400


class TrialBudgetTests(unittest.TestCase):
    def rig(self, **kwargs):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        rig = Rig(tmp.name, **kwargs)
        self.addCleanup(lambda: rig.gateway.close())
        return rig

    def restart(self, rig):
        rig.gateway.close()
        rig.gateway = CloudGateway(rig.gateway.config, rig.tmp / 'gw' / 'ledger.sqlite3', rig.provider, TOKENS,
                                   clock=rig.gateway.clock)
        rig.transport.gateway = rig.gateway

    def reservation(self, rig):
        return rig.gateway.reservation(c.validate_request(request()))

    def test_budget_is_cumulative_across_days_and_restarts(self):
        rig = self.rig(gateway=gateway_config(user_budget=10**8, global_budget=10**8))
        now = [1_800_000_000.0]
        rig.gateway.clock = lambda: now[0]
        reserve = self.reservation(rig)
        rig.gateway.ledger.start_trial('piloto-real-1', reserve + 100)
        self.assertEqual(rig.adapter.converse(request('trial-0001'))['status'], 'ok')
        charged = rig.row('trial-0001')['charged']
        self.assertEqual(rig.adapter.converse(request('trial-0002'))['error']['code'], 'budget_exhausted')
        for _ in range(3):  # new UTC days and a gateway restart do not refill it
            now[0] += DAY
            self.restart(rig)
            self.assertEqual(rig.adapter.converse(request(f'trial-1{int(now[0]) % 1000:03d}'))['error']['code'],
                             'budget_exhausted')
        self.assertEqual(len(rig.provider.calls), 1)
        trial = rig.gateway.ledger.trial()
        self.assertEqual((trial['charged_micro_usd'], trial['open_micro_usd']), (charged, 0))
        self.assertEqual(rig.gateway.status()['trial']['name'], 'piloto-real-1')

    def test_uncertain_reservations_count_until_reconciled_and_nothing_is_retried(self):
        rig = self.rig(provider=SimulatedProvider('lost'), gateway=gateway_config(user_budget=10**8, global_budget=10**8))
        now = [1_800_000_000.0]
        rig.gateway.clock = lambda: now[0]
        reserve = self.reservation(rig)
        rig.gateway.ledger.start_trial('piloto-real-1', 2 * reserve - 1)
        self.assertEqual(rig.adapter.converse(request('trial-0001'))['error']['code'], 'outcome_uncertain')
        self.assertEqual(rig.gateway.ledger.trial()['open_micro_usd'], reserve)
        now[0] += DAY
        self.restart(rig)
        rig.provider.behaviour = 'ok'
        self.assertEqual(rig.adapter.converse(request('trial-0002'))['error']['code'], 'budget_exhausted')
        self.assertEqual(rig.adapter.converse(request('trial-0001'))['error']['code'], 'outcome_uncertain')
        self.assertEqual(len(rig.provider.calls), 1)  # neither the uncertain one nor the blocked one is retried
        rig.gateway.ledger.reconcile('user-a', 'trial-0001', 300)
        self.assertEqual(rig.adapter.converse(request('trial-0003'))['status'], 'ok')
        self.assertEqual(len(rig.provider.calls), 2)

    def test_trial_cannot_be_raised_or_reopened_silently(self):
        rig = self.rig()
        ledger = rig.gateway.ledger
        first = ledger.start_trial('piloto-real-1', 1_000_000)
        self.assertEqual(ledger.start_trial('piloto-real-1', 1_000_000), first)  # restart with same flags
        with self.assertRaises(LedgerError):
            ledger.start_trial('piloto-real-1', 2_000_000)
        with self.assertRaises(LedgerError):
            ledger.start_trial('otra', 1_000_000)
        ledger.close_trial('piloto-real-1')
        with self.assertRaises(LedgerError):
            ledger.start_trial('piloto-real-1', 1_000_000)
        self.assertEqual(ledger.start_trial('piloto-real-2', 1_000_000)['remaining_micro_usd'], 1_000_000)

    def test_closing_the_trial_on_a_running_gateway_stops_sending(self):
        rig = self.rig()
        rig.gateway.ledger.start_trial('piloto-real-1', 1_000_000)
        self.assertEqual(rig.adapter.converse(request())['status'], 'ok')
        # Closed from another process (python -m arkos_cloud trial close) while the gateway keeps running.
        other = Ledger(rig.tmp / 'gw' / 'ledger.sqlite3')
        other.close_trial('piloto-real-1')
        other.close()
        calls = len(rig.provider.calls)
        result = rig.adapter.converse(request('trial-req-closed'))
        self.assertEqual(result['error']['code'], 'budget_exhausted', result)
        self.assertEqual(len(rig.provider.calls), calls)  # never falls back to "no cap"

    def test_real_provider_never_runs_without_a_trial(self):
        rig = self.rig()
        with self.assertRaises(ValueError):
            _open_trial(rig.gateway.ledger, None, None, 'real')
        with self.assertRaises(ValueError):
            _open_trial(rig.gateway.ledger, 'solo-nombre', None, 'test')
        self.assertIsNone(_open_trial(rig.gateway.ledger, None, None, 'test'))
        trial = _open_trial(rig.gateway.ledger, 'piloto-real-1', 1_000_000, 'real')
        self.assertEqual(trial['limit_micro_usd'], 1_000_000)
        self.assertEqual(_open_trial(rig.gateway.ledger, None, None, 'real')['name'], 'piloto-real-1')  # persisted

    def test_latency_is_recorded_per_turn(self):
        hold = threading.Event()
        rig = self.rig(provider=SimulatedProvider(hold=hold))
        timer = threading.Timer(0.25, hold.set)
        timer.start()
        self.assertEqual(rig.adapter.converse(request('lat-0001'))['status'], 'ok')
        self.assertGreaterEqual(rig.row('lat-0001')['latency_ms'], 200)
        rig.provider.hold = None
        rig.provider.behaviour = 'lost'
        rig.adapter.converse(request('lat-0002'))
        self.assertIsNotNone(rig.row('lat-0002')['latency_ms'])  # uncertain turns keep their latency too
        self.assertEqual(len(rig.gateway.ledger.latencies()), 1)    # only completed calls feed the percentiles

    def test_percentiles_need_a_real_sample(self):
        self.assertIsNone(_percentile([1000] * 5, 95))
        sample = list(range(100, 2100, 100))  # 20 turns
        self.assertEqual((_percentile(sample, 50), _percentile(sample, 95)), (1000, 1900))

    def test_v2_ledger_is_upgraded_in_place(self):
        tmp = Path(tempfile.mkdtemp())
        path = tmp / 'v2.sqlite3'
        db = sqlite3.connect(path)
        db.executescript("""
            CREATE TABLE calls (user_id TEXT NOT NULL, request_id TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL,
              day TEXT NOT NULL, reserved INTEGER NOT NULL, charged INTEGER NOT NULL DEFAULT 0,
              cancel_requested INTEGER NOT NULL DEFAULT 0, overrun INTEGER NOT NULL DEFAULT 0, response TEXT,
              created REAL NOT NULL, updated REAL NOT NULL, PRIMARY KEY (user_id, request_id));
            CREATE TABLE spend (scope TEXT NOT NULL, day TEXT NOT NULL, reserved INTEGER NOT NULL DEFAULT 0,
              charged INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (scope, day));
            CREATE TABLE tokens (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, created REAL NOT NULL, revoked REAL);
            INSERT INTO calls VALUES ('u','r-00000001','d','uncertain','2026-10-01',500,0,0,0,NULL,1,1);
            PRAGMA user_version=2;""")
        db.close()
        ledger = Ledger(path)
        try:
            self.assertEqual(ledger.db.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(ledger.get('u', 'r-00000001')['reserved'], 500)
            self.assertIn('latency_ms', ledger.get('u', 'r-00000001'))
            self.assertIsNone(ledger.trial())
        finally:
            ledger.close()


if __name__ == '__main__':
    unittest.main()
