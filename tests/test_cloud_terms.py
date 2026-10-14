"""Provider-terms record: a flag flip never enables a real provider. No network, keys or calls."""
import copy
from datetime import date
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from arkos_cloud import terms
from arkos_cloud.__main__ import KEY_FILE_ENV, _provider_key
from arkos_cloud.config import ClientConfig, GatewayConfig
from arkos_cloud.gateway import CloudGateway
from arkos_cloud.provider_anthropic import AnthropicProvider
from arkos_cloud.server import GatewayServer
from arkos_pilot.cloud_link import CloudLink
from tests.cloud_support import TOKEN_A, TOKENS, InProcessTransport, SimulatedProvider

ROOT = Path(__file__).resolve().parents[1]
CLIENT = json.loads((ROOT / 'config' / 'cloud-client.example.json').read_text(encoding='utf-8'))
GATEWAY = json.loads((ROOT / 'config' / 'cloud-gateway.example.json').read_text(encoding='utf-8'))
TODAY = date(2026, 10, 14)


def disclosure(**over):
    return ClientConfig.from_mapping(dict(CLIENT, disclosure=dict(CLIENT['disclosure'], **over))).disclosure


def completed(record):
    """What a finished human review looks like: every check with evidence, discrepancy resolved."""
    done = copy.deepcopy(record)
    for source in done['public_sources']:
        source['read_directly'] = True
    for check in done['account_checks']:
        check.update(status='confirmed', evidence='captura interna #'+check['id'], confirmed_by='Jona', confirmed_on='2026-10-20')
    for issue in done['discrepancies']:
        issue['status'] = 'resolved'
    return done


class TermsRecordTests(unittest.TestCase):
    def setUp(self):
        self.record, self.digest = terms.load()

    def test_repo_record_matches_the_consent_and_lists_what_is_pending(self):
        verdict = terms.evaluate(self.record, disclosure(), today=TODAY)
        self.assertEqual(verdict['problems'], [])
        self.assertFalse(verdict['ok'])
        pending = '\n'.join(verdict['pending'])
        for check in self.record['account_checks']:
            self.assertIn(check['item'], pending)
        self.assertIn('Discrepancia abierta', pending)
        self.assertIn('privacy.claude.com', pending)       # not read directly yet
        self.assertIn('terms_verified', pending)
        self.assertEqual(GATEWAY['disclosure'], CLIENT['disclosure'])

    def test_flipping_the_flag_alone_verifies_nothing(self):
        verdict = terms.evaluate(self.record, disclosure(terms_verified=True), today=TODAY)
        self.assertFalse(verdict['ok'])
        self.assertTrue(verdict['pending'])

    def test_a_completed_review_is_required_and_enough(self):
        verdict = terms.evaluate(completed(self.record), disclosure(terms_verified=True), today=TODAY)
        self.assertEqual((verdict['ok'], verdict['problems'], verdict['pending']), (True, [], []))

    def test_declared_values_must_equal_what_the_screen_shows(self):
        for field, value in [('provider_retention_days', 0), ('region', 'us'), ('provider_trains_on_data', True),
                             ('provider_flagged_retention_days', 30), ('model', 'claude-sonnet-5-5'),
                             ('provider_storage_region', 'eu')]:
            with self.subTest(field=field):
                verdict = terms.evaluate(completed(self.record), disclosure(terms_verified=True, **{field: value}), today=TODAY)
                self.assertFalse(verdict['ok'])
                self.assertTrue(any('no coincide' in p for p in verdict['problems']))

    def test_sources_must_be_official_recent_and_cover_each_claim(self):
        cases = []
        bad = completed(self.record); bad['public_sources'][0]['url'] = 'https://blog.example.com/anthropic-retention'; cases.append(bad)
        bad = completed(self.record); bad['public_sources'][0]['url'] = 'http://platform.claude.com/docs'; cases.append(bad)
        bad = completed(self.record); [s.update(retrieved_on='2026-06-01') for s in bad['public_sources']]; cases.append(bad)
        bad = completed(self.record); bad['valid_until'] = '2026-10-13'; cases.append(bad)
        bad = completed(self.record); [s.update(supports=[k for k in s['supports'] if k != 'storage_region']) for s in bad['public_sources']]; cases.append(bad)
        for record in cases:
            self.assertFalse(terms.evaluate(record, disclosure(terms_verified=True), today=TODAY)['ok'])
        unconfirmed = completed(self.record); unconfirmed['account_checks'][0]['evidence'] = None
        self.assertFalse(terms.evaluate(unconfirmed, disclosure(terms_verified=True), today=TODAY)['ok'])

    def test_record_holds_no_secrets(self):
        raw = (ROOT / 'config' / 'cloud-terms-record.json').read_text(encoding='utf-8')
        for marker in ('sk-ant', 'akc_', 'api_key', 'Bearer '):
            self.assertNotIn(marker, raw)


class RealActivationTests(unittest.TestCase):
    """The PC refuses a real provider unless the record is complete and the gateway uses the same one."""

    def build(self, record, flag):
        tmp = Path(tempfile.mkdtemp())
        path = tmp / 'terms.json'
        path.write_text(json.dumps(record), encoding='utf-8')
        data = dict(GATEWAY, disclosure=dict(GATEWAY['disclosure'], terms_verified=flag))
        provider = SimulatedProvider()
        provider.mode = 'real'
        gateway = CloudGateway(GatewayConfig.from_mapping(data), tmp / 'gw' / 'l.sqlite3', provider, TOKENS,
                               terms_digest=terms.load(path)[1])
        self.addCleanup(gateway.close)
        client = ClientConfig.from_mapping(dict(CLIENT, disclosure=data['disclosure']))
        link = CloudLink(tmp / 'pc', client, TOKEN_A, transport=InProcessTransport(gateway), terms_path=path)
        self.addCleanup(link.close)
        return link, gateway

    def test_flag_without_completed_record_is_blocked(self):
        record, _ = terms.load()
        link, _ = self.build(record, True)
        self.assertEqual(link.activation(refresh=True)['state'], 'blocked')
        self.assertIn('no están verificadas', link.activation()['reason'])

    def test_completed_record_and_same_digest_allows_consent(self):
        record, _ = terms.load()
        with patch('arkos_cloud.terms.date') as fake_date:
            fake_date.today.return_value = TODAY
            fake_date.fromisoformat = date.fromisoformat
            link, gateway = self.build(completed(record), True)
            self.assertEqual(link.activation(refresh=True)['state'], 'needs_consent')
            self.assertTrue(link.status()['terms']['ok'])
            gateway.terms_digest = 'otro'
            self.assertIn('otro registro', link.activation(refresh=True)['reason'])


class ServerSideTests(unittest.TestCase):
    def test_provider_key_file_must_be_private(self):
        if os.name == 'nt':
            self.skipTest('permisos POSIX')
        tmp = Path(tempfile.mkdtemp())
        key = tmp / 'key'
        key.write_text('synthetic-not-a-key\n', encoding='utf-8')
        key.chmod(0o644)
        with patch.dict(os.environ, {KEY_FILE_ENV: str(key)}, clear=False):
            with self.assertRaises(ValueError):
                _provider_key()
            key.chmod(0o600)
            self.assertEqual(_provider_key(), 'synthetic-not-a-key')

    def test_rate_limit_uses_forwarded_address_only_from_a_local_proxy(self):
        tmp = Path(tempfile.mkdtemp())
        gateway = CloudGateway(GatewayConfig.from_mapping(GATEWAY), tmp / 'l.sqlite3', SimulatedProvider(), TOKENS)
        self.addCleanup(gateway.close)
        with self.assertRaises(ValueError):
            GatewayServer(gateway, trusted_proxy='10.0.0.5', access_log=None)
        server = GatewayServer(gateway, trusted_proxy='127.0.0.1', access_log=None)
        self.addCleanup(server.server_close)
        handler = SimpleNamespace(client_address=('127.0.0.1', 1), server=server,
                                  headers={'X-Forwarded-For': 'spoofed, 203.0.113.9'})
        from arkos_cloud.server import _Handler
        self.assertEqual(_Handler._client_ip(handler), '203.0.113.9')
        handler.client_address = ('192.0.2.1', 1)
        self.assertEqual(_Handler._client_ip(handler), '192.0.2.1')

    def test_declared_inference_geo_is_sent_and_enforced(self):
        calls = []

        class Messages:
            def create(self, **kwargs):
                calls.append(kwargs)
                usage = SimpleNamespace(input_tokens=10, output_tokens=5, cache_creation_input_tokens=0,
                                        cache_read_input_tokens=0, inference_geo='global')
                return SimpleNamespace(usage=usage, stop_reason='end_turn',
                                       content=[SimpleNamespace(type='text', text='hola')])

        class Client:
            def __init__(self, **kwargs):
                self.messages = Messages()

            def close(self):
                pass

        sdk = SimpleNamespace(Anthropic=Client, APIConnectionError=type('E1', (Exception,), {}),
                              APIStatusError=type('E2', (Exception,), {}))
        for geo, text in (('global', 'hola'), ('us', '')):
            provider = AnthropicProvider('claude-haiku-5-5', 'synthetic', sdk=sdk, inference_geo=geo)
            result = provider.complete('s', [dict(role='user', content='x')], 64, 10, None)
            self.assertEqual(calls[-1]['inference_geo'], geo)
            self.assertEqual(result.text, text)  # "us" promised, "global" served: content discarded
        with self.assertRaises(ValueError):
            AnthropicProvider('claude-haiku-5-5', 'synthetic', sdk=sdk, inference_geo='eu')


class BackupTests(unittest.TestCase):
    def test_online_backup_is_consistent_rotated_and_private(self):
        import subprocess, sys
        from arkos_cloud.ledger import Ledger
        tmp = Path(tempfile.mkdtemp())
        ledger = Ledger(tmp / 'l.sqlite3')
        token = ledger.issue_token('pilot')
        try:
            outputs = []
            for _ in range(3):
                run = subprocess.run([sys.executable, '-B', '-m', 'arkos_cloud', 'backup', '--ledger', str(tmp / 'l.sqlite3'),
                                      '--out', str(tmp / 'bk'), '--keep', '2'], cwd=ROOT, capture_output=True, text=True, timeout=60)
                self.assertEqual(run.returncode, 0, run.stderr)
                outputs.append(run.stdout.strip())
                import time; time.sleep(1.1)
        finally:
            ledger.close()
        copies = sorted((tmp / 'bk').glob('ledger-*.sqlite3'))
        self.assertEqual(len(copies), 2)
        restored = Ledger(copies[-1])
        try:
            from arkos_cloud.ledger import token_hash
            self.assertEqual(restored.user_for(token_hash(token)), 'pilot')
        finally:
            restored.close()
        if os.name != 'nt':
            self.assertEqual(copies[-1].stat().st_mode & 0o077, 0)


if __name__ == '__main__':
    unittest.main()
