"""Selection and real chat integration, with an in-process synthetic model only."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from arkos_hermes import contract as c
from arkos_pilot.chat import Conversations, ChatError
from arkos_pilot.providers import select_provider
from arkos_pilot.task_center import TaskCenter

REQUEST = dict(v=1, request_id='provider-test-01', messages=[dict(role='user', content='Hola')])


class SpyProvider:
    def __init__(self, result=None):
        self.calls = 0
        self.result = result

    def converse(self, request, cancel_event=None):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result or c.response(request['request_id'], 'ok', reply='Prueba')


class ProviderSelectionTests(unittest.TestCase):
    def wait_turn(self, chat):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            turn = chat.get(REQUEST['request_id'])
            if turn['state'] != 'waiting':
                return turn
            threading.Event().wait(.005)
        self.fail('El turno no finalizó')

    def test_unconfigured_does_not_invent_provider(self):
        with tempfile.TemporaryDirectory() as root:
            chat = Conversations(root)
            self.assertEqual(chat.status()['processing'], 'unconfigured')
            with self.assertRaises(ChatError):
                chat.start(REQUEST)
            self.assertEqual(list(Path(root).iterdir()), [])
            chat.close()

    def test_existing_modes_remain_compatible(self):
        for mode, processing in [('hermes', 'local'), ('synthetic', 'synthetic')]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                spy = SpyProvider()
                chat = Conversations(root, spy, mode)
                try:
                    self.assertEqual(chat.status()['mode'], mode)
                    self.assertEqual(chat.status()['processing'], processing)
                    chat.start(REQUEST)
                    self.assertEqual(self.wait_turn(chat)['response']['reply'], 'Prueba')
                    self.assertEqual(spy.calls, 1)
                    self.assertEqual(list(Path(root).iterdir()), [])
                finally:
                    chat.close()

    def test_cloud_and_unknown_rejected_before_state_or_server(self):
        for mode in ['cloud', 'auto', 'gemini', '', None]:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                state = Path(root) / 'absent'
                spy = SpyProvider()
                with patch('arkos_pilot.task_center.ThreadingHTTPServer.__init__') as server:
                    with self.assertRaises(ValueError):
                        TaskCenter(state, bridge=spy, chat_mode=mode)
                    server.assert_not_called()
                self.assertFalse(state.exists())
                self.assertEqual(spy.calls, 0)

    def test_cloud_without_bridge_is_still_rejected(self):
        with self.assertRaises(ValueError):
            select_provider(None, 'cloud')

    def test_invalid_adapter_rejected_without_call(self):
        for bridge in [object(), type('Bad', (), {'converse': 1})()]:
            with self.assertRaises(ValueError):
                select_provider(bridge)

    def test_failure_calls_selected_adapter_once_and_never_falls_back(self):
        with tempfile.TemporaryDirectory() as root:
            spy = SpyProvider(RuntimeError('private diagnostic'))
            chat = Conversations(root, spy)
            try:
                chat.start(REQUEST)
                response = self.wait_turn(chat)['response']
                self.assertEqual(response['status'], 'error')
                self.assertEqual(response['proposals'], [])
                self.assertEqual(response['reply'], '')
                self.assertNotIn('private diagnostic', str(response))
                self.assertEqual(spy.calls, 1)
            finally:
                chat.close()

    def test_provider_cannot_return_usable_content_on_failure(self):
        with tempfile.TemporaryDirectory() as root:
            body = c.response(REQUEST['request_id'], 'error', error=('model_error', 'failure'))
            body['reply'] = 'Aprobado y ejecutado'
            chat = Conversations(root, SpyProvider(body), 'synthetic')
            try:
                chat.start(REQUEST)
                result = self.wait_turn(chat)['response']
                self.assertEqual(result['reply'], '')
                self.assertEqual(result['proposals'], [])
                self.assertEqual(list(Path(root).iterdir()), [])
            finally:
                chat.close()


if __name__ == '__main__':
    unittest.main()
