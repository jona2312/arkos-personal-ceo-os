"""Rejected POSTs: the response must survive on every OS (Windows resets on unread bytes)."""
import http.client
import json
import socket
import tempfile
import threading
import time
import unittest

from arkos_pilot.task_center import DRAIN_LIMIT, DRAIN_SECONDS, TaskCenter


class RejectedBodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = TaskCenter(self.tmp.name)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start()
        self.host = self.server.origin.split('//')[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def open(self, length, key='wrong', extra=''):
        sock = socket.create_connection(('127.0.0.1', self.server.server_port), timeout=3)
        self.addCleanup(sock.close)
        sock.sendall((f'POST /api/tasks HTTP/1.1\r\nHost: {self.host}\r\nOrigin: {self.server.origin}\r\n'
                      f'X-Arkos-Key: {key}\r\nContent-Type: application/json\r\n{extra}'
                      f'Content-Length: {length}\r\n\r\n').encode())
        return sock

    def read_response(self, sock):
        data = b''
        while b'\r\n\r\n' not in data:
            data += sock.recv(4096)
        head, _, body = data.partition(b'\r\n\r\n')
        size = int([l for l in head.split(b'\r\n') if l.lower().startswith(b'content-length:')][0].split(b':')[1])
        while len(body) < size:
            body += sock.recv(4096)
        return int(head.split()[1]), json.loads(body)

    def closed_within(self, sock, seconds):
        sock.settimeout(seconds)
        try:
            return sock.recv(1) == b''
        except socket.timeout:
            return False

    def test_small_body_is_drained_before_close(self):
        body = json.dumps({'action': 'note', 'text': 'x'}).encode()
        sock = self.open(len(body))
        self.assertEqual(self.read_response(sock)[0], 401)
        # Without draining, the server closed here, before the body arrived (RST on Windows).
        self.assertFalse(self.closed_within(sock, 0.2))
        sock.sendall(body)
        self.assertTrue(self.closed_within(sock, 2))

    def test_large_chunked_or_missing_bodies_are_not_waited_for(self):
        cases = [(DRAIN_LIMIT + 1, ''), (10_000_000, ''), (5, 'Transfer-Encoding: chunked\r\n')]
        for length, extra in cases:
            with self.subTest(length=length, extra=extra):
                started = time.monotonic()
                sock = self.open(length, extra=extra)
                self.assertEqual(self.read_response(sock)[0], 401)
                self.assertTrue(self.closed_within(sock, 1))
                self.assertLess(time.monotonic() - started, 1.5)
        started = time.monotonic()
        sock = self.open(1000)  # declares a small body and never sends it
        self.assertEqual(self.read_response(sock)[0], 401)
        self.assertTrue(self.closed_within(sock, DRAIN_SECONDS + 1))
        self.assertLess(time.monotonic() - started, DRAIN_SECONDS + 1.5)

    def test_authentication_is_unchanged_and_body_never_used(self):
        body = json.dumps({'action': 'note', 'text': 'no debe crearse'}).encode()
        sock = self.open(len(body))
        sock.sendall(body)
        status, value = self.read_response(sock)
        self.assertEqual(status, 401)
        self.assertNotIn('no debe crearse', json.dumps(value))
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        conn.request('GET', '/api/tasks', headers={'X-Arkos-Key': self.server.key})
        self.assertEqual(json.loads(conn.getresponse().read())['tasks'], [])
        conn.close()

    def test_repeated_rejections_are_always_readable(self):
        """The CI symptom (WinError 10053 on Windows 3.12) as a loop over http.client."""
        for method, path, body in [('POST', '/api/chat/request-0001/cancel', {}),
                                   ('POST', '/api/chat/request-0001/note', {'proposal_id': 'prp_' + '0' * 24}),
                                   ('POST', '/api/tasks', {'action': 'note', 'text': 'x'})] * 10:
            conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
            conn.request(method, path, json.dumps(body),
                         {'X-Arkos-Key': 'another-session', 'Origin': self.server.origin,
                          'Content-Type': 'application/json'})
            response = conn.getresponse()
            self.assertEqual(response.status, 401)
            json.loads(response.read())
            conn.close()


if __name__ == '__main__':
    unittest.main()
