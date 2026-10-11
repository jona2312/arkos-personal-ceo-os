"""Cloud from the task center (HTTP, same session auth) against an in-process gateway with a
synthetic provider. No network, keys or paid calls."""
import http.client
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from arkos_hermes import contract as c
from arkos_cloud.gateway import CloudGateway, utc_day
from arkos_pilot.cloud_link import CloudLink
from arkos_pilot.core import Queue
from arkos_pilot.providers import select_provider
from arkos_pilot.task_center import TaskCenter
from tests.cloud_support import (TOKEN_A, TOKENS, InProcessTransport, SimulatedProvider, client_config,
                                 gateway_config, matching_client_config)

PROPOSAL_TEXT = ('Te propongo una nota.\n```arkos-proposal\n'
                 '{"type": "note", "title": "Compras", "text": "Comprar café"}\n```')


class LocalSpy:
    def __init__(self):
        self.calls = []

    def converse(self, request, cancel_event=None):
        self.calls.append(request)
        return c.response(request['request_id'], 'ok', reply='Respuesta local')


class CloudCenterTests(unittest.TestCase):
    def setUp(self, gateway_cfg=None, provider=None):
        self.tmp = Path(tempfile.mkdtemp())
        self.provider = provider or SimulatedProvider(text=PROPOSAL_TEXT)
        cfg = gateway_cfg or gateway_config()
        self.gateway = CloudGateway(cfg, self.tmp / 'gw' / 'ledger.sqlite3', self.provider, TOKENS)
        self.transport = InProcessTransport(self.gateway)
        self.link = CloudLink(self.tmp / 'pc', matching_client_config(cfg), TOKEN_A, transport=self.transport)
        self.local = LocalSpy()
        self.start_center(cloud=self.link)

    def start_center(self, cloud):
        if getattr(self, 'server', None):
            self.stop_center()
        self.server = TaskCenter(self.tmp / 'pc', bridge=self.local, chat_mode='synthetic', cloud=cloud)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start()

    def stop_center(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.server = None

    def tearDown(self):
        if self.server:
            self.stop_center()
        self.gateway.close()

    def call(self, method, path, data=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'X-Arkos-Key': self.server.key, 'Origin': self.server.origin, 'Content-Type': 'application/json'}
        conn.request(method, path, json.dumps(data) if data is not None else None, headers)
        response = conn.getresponse()
        status, body = response.status, json.loads(response.read())
        conn.close()
        return status, body

    def accept(self):
        info = self.call('GET', '/api/cloud')[1]
        return self.call('POST', '/api/cloud/consent', {'code': info['consent_code']})

    def turn(self, rid, text='Anotá comprar café', history=(), prefix='/api/cloud/chat'):
        request = dict(v=1, request_id=rid, messages=[*history, dict(role='user', content=text)])
        status, view = self.call('POST', prefix, request)
        self.assertEqual(status, 202, view)
        deadline = time.monotonic() + 5
        while view['state'] == 'waiting' and time.monotonic() < deadline:
            time.sleep(0.02)
            view = self.call('GET', prefix + '/' + rid)[1]
        return view

    def conversation_posts(self):
        return [r for r in self.transport.requests if r['path'] == '/v1/conversations']

    def test_disabled_by_default(self):
        self.start_center(cloud=None)
        status, info = self.call('GET', '/api/cloud')
        self.assertEqual((status, info['configured']), (200, False))
        self.assertEqual(self.call('POST', '/api/cloud/chat', dict(v=1, request_id='cloud-ui-0001',
                                                                  messages=[dict(role='user', content='hola')]))[0], 404)
        self.assertFalse(self.call('GET', '/api/status')[1]['capabilities']['cloud_chat'])
        with self.assertRaises(ValueError):
            TaskCenter(self.tmp / 'other', bridge=self.link.guard, chat_mode='cloud')
        with self.assertRaises(ValueError):
            select_provider(self.link.adapter, 'cloud')
        self.assertEqual(select_provider(self.link.guard, 'cloud').processing, 'cloud')

    def test_consent_is_required_and_bound_to_the_shown_terms(self):
        info = self.call('GET', '/api/cloud')[1]
        self.assertEqual(info['activation']['state'], 'needs_consent')
        self.assertTrue(info['activation']['test'])
        d = info['disclosure']
        for key in ('provider', 'model', 'data_sent', 'gateway_retention_hours', 'provider_retention_days',
                    'terms_verified', 'limits_usd'):
            self.assertIn(key, d)
        self.assertEqual(d['limits_usd'], dict(per_user_daily=0.1, global_daily=1.0, global_monthly=31.0))
        view = self.turn('cloud-ui-0001')
        self.assertEqual((view['state'], view['response']['error_code']), ('error', 'consent_required'))
        self.assertEqual(self.conversation_posts(), [])
        self.assertEqual(self.call('POST', '/api/cloud/consent', {'code': '000000000000'})[0], 400)
        status, info = self.accept()
        self.assertEqual((status, info['activation']['state']), (200, 'ready'))
        view = self.turn('cloud-ui-0002')
        self.assertEqual(view['state'], 'ok')
        self.assertEqual(len(self.provider.calls), 1)
        status, info = self.call('POST', '/api/cloud/revoke', {})
        self.assertEqual(info['activation']['state'], 'needs_consent')
        self.assertEqual(self.turn('cloud-ui-0003')['response']['error_code'], 'consent_required')
        self.assertEqual(len(self.provider.calls), 1)

    def test_real_provider_with_unverified_terms_is_blocked(self):
        self.provider.mode = 'real'
        info = self.call('GET', '/api/cloud')[1]
        self.assertEqual(info['activation']['state'], 'blocked')
        self.assertIn('no están verificadas', info['activation']['reason'])
        self.assertEqual(self.accept()[0], 409)
        view = self.turn('cloud-ui-0001')
        self.assertEqual(view['response']['error_code'], 'unsafe_configuration')
        self.assertEqual(self.provider.calls, [])

    def test_gateway_terms_different_from_the_screen_block_activation(self):
        self.accept()
        self.gateway.config = gateway_config(model='otro-modelo')
        self.link._checked = 0
        info = self.call('GET', '/api/cloud')[1]
        self.assertEqual(info['activation']['state'], 'blocked')
        self.assertEqual(self.turn('cloud-ui-0001')['response']['error_code'], 'unsafe_configuration')
        self.assertEqual(self.provider.calls, [])

    def test_local_history_is_never_sent_to_cloud(self):
        self.accept()
        local = self.turn('local-ui-0001', 'Algo privado de la PC', prefix='/api/chat')
        self.assertEqual(local['state'], 'ok')
        leaked = [dict(role='user', content='Algo privado de la PC'), dict(role='assistant', content='Respuesta local')]
        view = self.turn('cloud-ui-0001', 'seguí', history=leaked)
        self.assertEqual(view['response']['error_code'], 'invalid_request')
        self.assertEqual(self.provider.calls, [])
        first = self.turn('cloud-ui-0002', 'Anotá comprar café')
        own = [dict(role='user', content='Anotá comprar café'), dict(role='assistant', content=first['response']['reply'])]
        self.assertEqual(self.turn('cloud-ui-0003', 'y leche', history=own)['state'], 'ok')
        self.assertEqual([len(call['messages']) for call in self.provider.calls], [1, 3])
        for call in self.provider.calls:
            self.assertNotIn('Algo privado de la PC', json.dumps(call['messages']))

    def test_proposal_becomes_a_pending_task_only(self):
        self.accept()
        view = self.turn('cloud-ui-0001')
        proposal = view['response']['proposals'][0]
        status, body = self.call('POST', '/api/cloud/chat/cloud-ui-0001/note', {'proposal_id': proposal['proposal_id']})
        self.assertEqual(status, 200)
        self.assertEqual((body['task']['state'], body['task']['approval_until']), ('awaiting_approval', None))
        again = self.call('POST', '/api/cloud/chat/cloud-ui-0001/note', {'proposal_id': proposal['proposal_id']})[1]
        self.assertEqual(again['task']['id'], body['task']['id'])
        queue = Queue(self.tmp / 'pc')
        try:
            self.assertEqual([t['state'] for t in queue.list()], ['awaiting_approval'])
            key = queue.db.execute('SELECT source_key FROM task_sources').fetchone()[0]
        finally:
            queue.close()
        self.assertTrue(key.startswith('cloud:cloud-ui-0001:'))
        self.assertEqual(list((self.tmp / 'pc' / 'outputs').iterdir()), [])

    def test_states_budget_uncertain_cancel_and_no_automatic_retry(self):
        self.accept()
        self.gateway.ledger.reserve('other', 'seed-0001', 'd', 1_000_000, utc_day(), 10**9, 10**9)
        self.assertEqual(self.turn('cloud-ui-0001')['response']['error_code'], 'budget_exhausted')
        self.gateway.ledger.request_cancel('other', 'seed-0001')
        self.provider.behaviour = 'lost'
        view = self.turn('cloud-ui-0002')
        self.assertEqual(view['response']['error_code'], 'outcome_uncertain')
        self.assertEqual(self.call('GET', '/api/cloud/chat/cloud-ui-0002/check')[1]['state'], 'uncertain')
        posts = len(self.conversation_posts())  # the budget refusal also reached the gateway, which refused it
        resend = self.call('POST', '/api/cloud/chat', view['request'])[1]   # same turn: replayed, not resent
        self.assertEqual(resend['state'], 'error')
        self.assertEqual(len(self.conversation_posts()), posts)
        self.assertEqual(len(self.provider.calls), 1)
        self.gateway.ledger.reconcile('user-a', 'cloud-ui-0002', 0)
        hold = threading.Event()
        self.provider.behaviour, self.provider.hold = 'ok', hold
        self.provider.entered.clear()
        request = dict(v=1, request_id='cloud-ui-0003', messages=[dict(role='user', content='otra')])
        self.assertEqual(self.call('POST', '/api/cloud/chat', request)[0], 202)
        self.assertTrue(self.provider.entered.wait(5))
        self.assertEqual(self.call('POST', '/api/cloud/chat/cloud-ui-0003/cancel', {})[1]['state'], 'cancelled')
        deadline = time.monotonic() + 5
        while self.gateway.ledger.get('user-a', 'cloud-ui-0003')['cancel_requested'] == 0 and time.monotonic() < deadline:
            time.sleep(0.02)
        hold.set()
        while self.gateway.ledger.get('user-a', 'cloud-ui-0003')['state'] == 'sent' and time.monotonic() < deadline:
            time.sleep(0.02)
        row = self.gateway.ledger.get('user-a', 'cloud-ui-0003')
        self.assertEqual(row['state'], 'cancelled')
        self.assertGreater(row['charged'], 0)  # cancelling stopped the wait, not the bill

    def test_cloud_routes_keep_the_local_session_auth(self):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request('GET', '/api/cloud', headers={'X-Arkos-Key': 'wrong'})
        self.assertEqual(conn.getresponse().status, 401)
        conn.close()
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request('POST', '/api/cloud/consent', json.dumps({'code': 'x'}),
                     {'X-Arkos-Key': self.server.key, 'Origin': 'http://evil.example', 'Content-Type': 'application/json'})
        self.assertEqual(conn.getresponse().status, 403)
        conn.close()
        self.assertEqual(self.call('GET', '/api/cloud')[1]['activation']['state'], 'needs_consent')


if __name__ == '__main__':
    unittest.main()
