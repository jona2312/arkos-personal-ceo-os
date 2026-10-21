import base64
import concurrent.futures
import io
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import threading
import unittest
from unittest.mock import patch
import uuid
import wave

from arkos_pilot.dictation import Dictation, decode_audio
from arkos_pilot.chat import ChatError
from arkos_pilot.task_center import TaskCenter


def audio_request(rate=16000, seconds=.2):
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        wav.writeframes(b'\x00\x00' * int(rate * seconds))
    return {'request_id': 'dict-' + str(uuid.uuid4()), 'audio': base64.b64encode(output.getvalue()).decode()}


class DictationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name in ('config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt'):
            (self.root/name).touch()
        self.dictation = Dictation(sys.executable, self.root)

    def tearDown(self):
        self.dictation.close()
        self.tmp.cleanup()

    def worker(self, text='Texto editable', delay=0, fail=False):
        # Real bounded child process, synthetic recognition; no STT dependency in CI.
        original = subprocess.Popen
        code = ('import sys,time,json; sys.stdin.buffer.read(); time.sleep('+str(delay)+'); '
                + ('sys.exit(1)' if fail else 'print(json.dumps({"text":'+repr(text)+'}))'))
        return patch('arkos_pilot.dictation.subprocess.Popen',
                     side_effect=lambda args, **kw: original([sys.executable, '-I', '-c', code], **kw))

    def test_validated_audio_only(self):
        self.assertTrue(decode_audio(audio_request()))
        for request in (audio_request(rate=48000), audio_request(seconds=31),
                        dict(audio_request(), command='whoami'), dict(audio_request(), audio='!'),
                        dict(audio_request(), request_id='../escape')):
            with self.assertRaises(ValueError):
                decode_audio(request)

    def test_offline_configuration_requires_complete_local_files(self):
        (self.root/'tokenizer.json').unlink()
        with self.assertRaises(ValueError):
            Dictation(sys.executable, self.root)

    def test_text_only_no_audio_files_and_no_duplicate_inference(self):
        before = set(self.root.iterdir())
        request = audio_request()
        with self.worker('<script>not markup</script>'):
            result = self.dictation.transcribe(request)
            self.assertEqual(result['text'], '<script>not markup</script>')
            self.assertFalse(result['audio_saved'])
            with self.assertRaises(ChatError):
                self.dictation.transcribe(request)
        self.assertEqual(before, set(self.root.iterdir()))

    def test_cancel_before_start(self):
        request = audio_request()
        self.dictation.cancel(request['request_id'])
        with self.assertRaises(ChatError):
            self.dictation.transcribe(request)

    def test_cancel_and_concurrency(self):
        request = audio_request()
        with self.worker(delay=30), concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(self.dictation.transcribe, request)
            end = time.monotonic()+5
            while self.dictation.active is None and time.monotonic()<end:
                time.sleep(.01)
            self.assertIsNotNone(self.dictation.active)
            process = self.dictation.active['process']
            with self.assertRaises(ChatError):
                self.dictation.transcribe(audio_request())
            self.dictation.cancel(request['request_id'])
            with self.assertRaises(ChatError):
                future.result(timeout=5)
            self.assertIsNotNone(process.poll())

    def test_timeout_error_and_shutdown(self):
        self.dictation.timeout = .1
        with self.worker(delay=30), self.assertRaises(ChatError) as exc:
            self.dictation.transcribe(audio_request())
        self.assertEqual(exc.exception.status, 504)
        with self.worker(fail=True), self.assertRaises(ChatError):
            self.dictation.transcribe(audio_request())
        self.dictation.close()
        with self.assertRaises(ChatError):
            self.dictation.transcribe(audio_request())

    def test_http_auth_origin_and_nonblocking_task_reads(self):
        server = TaskCenter(self.root/'state', dictation=self.dictation)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
        thread.start()
        def call(method, path, data=None, overrides=None):
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            headers = {'X-Arkos-Key': server.key, 'Origin': server.origin, 'Content-Type': 'application/json'}
            headers.update(overrides or {})
            try:
                conn.request(method, path, json.dumps(data) if data is not None else None, headers)
                response = conn.getresponse()
                return response.status, json.loads(response.read())
            finally:
                conn.close()
        try:
            self.assertEqual(call('GET', '/api/dictation', overrides={'X-Arkos-Key': 'invalid'})[0], 401)
            self.assertEqual(call('POST', '/api/dictation', audio_request(),
                                  {'Origin': 'http://example.com'})[0], 403)
            self.assertEqual(call('GET', '/api/dictation')[1]['processing'], 'local')
            request = audio_request()
            with self.worker(delay=30), concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(call, 'POST', '/api/dictation', request)
                end = time.monotonic()+5
                while self.dictation.active is None and time.monotonic()<end:
                    time.sleep(.01)
                self.assertIsNotNone(self.dictation.active)
                self.assertEqual(call('GET', '/api/tasks')[1]['tasks'], [])
                self.assertEqual(call('POST', '/api/dictation/cancel', {'request_id': request['request_id']})[0], 200)
                self.assertEqual(future.result(timeout=5)[0], 409)
                self.assertEqual(call('GET', '/api/tasks')[1]['tasks'], [])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
