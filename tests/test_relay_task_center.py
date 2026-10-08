"""Joint producer/reader/loopback tests. Synthetic data; no real accounts."""
import copy
import http.client
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from arkos_pilot.relay_snapshot import MAX_BYTES, STATES, read_view
from arkos_pilot.task_center import TaskCenter, queue_at
from tests.test_relay_viewer import ViewerFixture


class RelayTaskCenterTests(ViewerFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.task('Pedido sintético', 'req-center-001', approve=True, target_device_id=self.device['device_id'])
        self.snapshot = self.viewer.sync()
        self.path = self.view_dir / 'relay-snapshot.json'

    def view(self):
        return read_view(self.path, self.device['device_id'], self.clock())

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding='utf-8')

    def test_producer_to_private_http_never_executes_or_copies(self):
        server = TaskCenter(self.dir / 'center', relay_snapshot=self.path, relay_device_id=self.device['device_id'])
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        thread.start()
        try:
            client = http.client.HTTPConnection('127.0.0.1', server.server_port)
            client.request('GET', '/api/remote-view')
            response = client.getresponse(); self.assertEqual(response.status, 401); response.read()
            with patch('arkos_pilot.relay_snapshot.time.time', self.clock):
                client.request('GET', '/api/remote-view', headers={'X-Arkos-Key': server.key})
                response = client.getresponse(); view = json.loads(response.read())
            self.assertEqual(response.status, 200)
            self.assertEqual(view['sync_status'], 'current')
            self.assertEqual(view['tasks'][0]['state'], 'approved')
            with queue_at(server.root) as queue:
                self.assertEqual(queue.list(), [])
            client.close()
            remote = self.call('GET', '/v1/tasks', token=self.alice_token)[1]['tasks'][0]
            self.assertEqual(remote['state'], 'approved')
            self.assertEqual(remote['attempts'], 0)
            self.assertFalse(self.outputs.exists())
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_freshness_recomputed_and_future_clock_is_not_fresh(self):
        self.clock.advance(121)
        self.assertEqual(self.view()['sync_status'], 'stale')
        self.clock.advance(-122)
        self.assertEqual(self.view()['sync_status'], 'stale')

    def test_offline_retains_copy_but_revocation_hides_it(self):
        self.transport.offline = True; self.viewer.sync()
        self.assertEqual(self.view()['sync_status'], 'offline')
        self.assertEqual(len(self.view()['tasks']), 1)
        self.transport.offline = False
        self.call('POST', f"/v1/devices/{self.device['device_id']}/viewer-tokens/revoke", {}, self.alice_token)
        self.viewer.sync()
        self.assertEqual(self.view()['sync_status'], 'unauthorized')
        self.assertEqual(self.view()['tasks'], [])

    def test_wrong_device_or_task_destination_rejected(self):
        self.assertEqual(read_view(self.path, 'dev_'+'0'*32)['sync_status'], 'unavailable')
        self.snapshot['tasks'][0]['target_device_id'] = 'dev_'+'0'*32
        self.write(self.snapshot); self.assertEqual(self.view()['tasks'], [])

    def test_all_nine_states_and_allowlisted_fields(self):
        for state in STATES:
            self.snapshot['tasks'][0]['state'] = state
            self.snapshot['token'] = 'secret-must-not-leak'
            self.snapshot['tasks'][0]['credentials'] = 'secret-must-not-leak'
            self.write(self.snapshot)
            view = self.view()
            self.assertEqual(view['tasks'][0]['state'], state)
            self.assertNotIn('secret-must-not-leak', json.dumps(view))
            self.assertNotIn('payload_sha256', json.dumps(view))

    def test_malformed_and_oversized_files_are_unavailable(self):
        for content in (b'{', b'[]', b'x'*(MAX_BYTES+1)):
            self.path.write_bytes(content)
            self.assertEqual(self.view()['sync_status'], 'unavailable')
        self.path.unlink(); self.assertEqual(self.view()['sync_status'], 'unavailable')

    def test_invalid_count_schema_dates_and_duplicates(self):
        cases = []
        for field, value in [('schema_version', True), ('task_count', 2), ('generated_at', float('nan'))]:
            case = copy.deepcopy(self.snapshot); case[field] = value; cases.append(case)
        case = copy.deepcopy(self.snapshot); case['tasks'] *= 2; case['task_count'] = 2; cases.append(case)
        case = copy.deepcopy(self.snapshot); case['tasks'][0]['result'] = []; cases.append(case)
        for case in cases:
            self.write(case); self.assertEqual(self.view()['sync_status'], 'unavailable')

    def test_partial_copy_and_unconfigured(self):
        self.snapshot['truncated'] = True; self.write(self.snapshot)
        self.assertTrue(self.view()['truncated'])
        self.assertEqual(read_view()['sync_status'], 'not_configured')
        with self.assertRaises(ValueError):
            TaskCenter(self.dir / 'invalid', relay_snapshot=self.path)

    def test_only_utf8_without_bom_is_accepted(self):
        content = json.dumps(self.snapshot, ensure_ascii=False)
        for data in (content.encode('utf-16'), content.encode('utf-32'), b'\xef\xbb\xbf' + content.encode('utf-8'), b'\xff'):
            self.path.write_bytes(data)
            self.assertEqual(self.view()['sync_status'], 'unavailable')
        self.path.write_bytes(content.encode('utf-8'))
        self.assertEqual(self.view()['sync_status'], 'current')
