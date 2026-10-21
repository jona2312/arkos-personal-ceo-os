"""Real process lifecycle, synthetic inference. Physical acceptance is separate."""
import concurrent.futures
import json
import http.client
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import threading
import unittest
from unittest.mock import patch
import uuid

from arkos_pilot.voice import Voice
from arkos_pilot.chat import ChatError
from tests.test_dictation import audio_request
from arkos_pilot.task_center import TaskCenter


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in ('config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt', 'voice.onnx', 'voice.onnx.json'):
            (self.root/name).touch()
        self.voice = Voice(sys.executable, self.root, self.root/'voice.onnx')
        self.sid = 'voice-'+str(uuid.uuid4())

    def tearDown(self):
        self.voice.close()
        self.tmp.cleanup()

    def request(self, **extra):
        return dict(session_id=self.sid, request_id='voice-'+str(uuid.uuid4()), **extra)

    def worker(self, delay=0):
        original = subprocess.Popen
        code = ('import sys,json,time\nfor line in sys.stdin:\n'
                ' r=json.loads(line); time.sleep('+str(delay)+')\n'
                ' print(json.dumps({"ready":True,"text":"Texto de prueba","worker_ms":1}),flush=True)\n')
        return patch('arkos_pilot.voice.subprocess.Popen',
                     side_effect=lambda args, **kw: original([sys.executable, '-I', '-c', code], **kw))

    def test_reuses_process_no_files_no_secrets_in_environment(self):
        before = set(self.root.iterdir())
        with self.worker() as spawn, patch.dict('os.environ', {'SECRET_TEST_KEY': 'must-not-pass'}):
            self.voice.call('warm', self.request())
            process = self.voice.process
            self.voice.call('transcribe', self.request(audio=audio_request()['audio']))
            self.assertIs(self.voice.process, process)
            self.assertEqual(spawn.call_count, 1)
            self.assertNotIn('SECRET_TEST_KEY', spawn.call_args.kwargs['env'])
        self.assertEqual(set(self.root.iterdir()), before)

    def test_validation_and_cancel_before_warm(self):
        for op, data in [('speak', self.request(text='x'*1001)), ('transcribe', self.request(audio='!')),
                         ('warm', self.request(command='whoami')), ('execute', self.request())]:
            with self.assertRaises(ValueError):
                self.voice.call(op, data)
        self.voice.call('cancel', self.request())
        with self.assertRaises(ChatError):
            self.voice.call('warm', self.request())
        self.assertIsNone(self.voice.process)

    def test_duplicate_and_other_session_rejected(self):
        request = self.request()
        with self.worker():
            self.voice.call('warm', request)
            with self.assertRaises(ChatError):
                self.voice.call('warm', request)
            other = self.request(); other['session_id'] = 'voice-'+str(uuid.uuid4())
            with self.assertRaises(ChatError):
                self.voice.call('warm', other)

    def test_cancel_kills_owned_process_and_discards_output(self):
        with self.worker(delay=20), concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(self.voice.call, 'warm', self.request())
            deadline = time.monotonic()+5
            while not self.voice.process and time.monotonic()<deadline:
                time.sleep(.01)
            process = self.voice.process
            self.assertIsNotNone(process)
            with self.assertRaises(ChatError):
                self.voice.call('warm', self.request())
            self.voice.call('cancel', self.request())
            with self.assertRaises(ChatError):
                future.result(timeout=5)
            self.assertIsNotNone(process.poll())

    def test_timeout_releases_process(self):
        self.voice.timeout = .1
        with self.worker(delay=20), self.assertRaises(ChatError) as error:
            self.voice.call('warm', self.request())
        self.assertEqual(error.exception.status, 504)
        self.assertIsNone(self.voice.process)

    def test_http_auth_origin_and_task_isolation(self):
        server = TaskCenter(self.root/'state', voice=self.voice)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
        thread.start()
        def call(method, route, data=None, override=None):
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            headers = {'X-Arkos-Key': server.key, 'Origin': server.origin, 'Content-Type': 'application/json'}
            headers.update(override or {})
            try:
                conn.request(method, route, json.dumps(data) if data is not None else None, headers)
                response = conn.getresponse()
                return response.status, json.loads(response.read())
            finally:
                conn.close()
        try:
            self.assertEqual(call('GET', '/api/voice', override={'X-Arkos-Key': 'invalid'})[0], 401)
            self.assertEqual(call('POST', '/api/voice/warm', self.request(), {'Origin': 'https://evil.example'})[0], 403)
            self.assertEqual(call('GET', '/api/voice', override={'Host': 'evil.example'})[0], 403)
            with self.worker(delay=20), concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(call, 'POST', '/api/voice/warm', self.request())
                deadline = time.monotonic()+5
                while not self.voice.process and time.monotonic()<deadline:
                    time.sleep(.01)
                self.assertEqual(call('GET', '/api/tasks')[1]['tasks'], [])
                self.assertEqual(call('POST', '/api/voice/cancel', self.request())[0], 200)
                self.assertEqual(future.result(timeout=5)[0], 409)
                self.assertEqual(call('GET', '/api/tasks')[1]['tasks'], [])
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__ == '__main__':
    unittest.main()
