"""Launch diagnostics and first-open isolation; no installs or real PC state."""
import http.client
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from arkos_pilot.launcher import main, preflight


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'prueba con espacios y ñ'

    def tearDown(self):
        self.temp.cleanup()

    def test_check_only_does_not_create_state_even_with_missing_optional_tools(self):
        with patch('arkos_pilot.launcher.shutil.which', return_value=None):
            report = preflight(self.root)
        self.assertTrue(report['ready'])
        self.assertFalse(report['capabilities']['clips'])
        self.assertFalse(report['capabilities']['hermes_chat'])
        self.assertTrue(report['warnings'])
        result = subprocess.run([sys.executable, '-B', '-m', 'arkos_pilot.launcher', '--state-dir', str(self.root), '--check-only'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['ready'])
        self.assertFalse(self.root.exists())

    def test_occupied_port_and_invalid_ports_block_without_creating_state(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); listener.listen()
            self.assertFalse(preflight(self.root, listener.getsockname()[1])['ready'])
        for port in (-1, 65536):
            self.assertFalse(preflight(self.root, port)['ready'])
        self.assertFalse(self.root.exists())

    def test_wrong_state_layout_is_not_overwritten(self):
        self.root.mkdir()
        for child, directory in [('outputs', False), ('queue.sqlite3', True)]:
            target = self.root / child
            if directory: target.mkdir()
            else: target.write_text('preservar', encoding='utf-8')
            self.assertFalse(preflight(self.root)['ready'])
            if directory: target.rmdir()
            else:
                self.assertEqual(target.read_text(encoding='utf-8'), 'preservar'); target.unlink()

    def test_partial_relay_config_blocks_but_missing_snapshot_only_warns(self):
        self.assertFalse(preflight(self.root, relay_snapshot=self.root / 'snapshot.json')['ready'])
        self.assertFalse(preflight(self.root, relay_snapshot=self.root / 'snapshot.json', relay_device_id='bad')['ready'])
        report = preflight(self.root, relay_snapshot=self.root / 'snapshot.json', relay_device_id='dev_'+'1'*32)
        self.assertTrue(report['ready'])
        self.assertTrue(report['warnings'])
        self.assertFalse(self.root.exists())

    def test_failed_launch_reports_error_instead_of_traceback(self):
        with patch('arkos_pilot.task_center.main', side_effect=PermissionError('private path')), patch('sys.stderr') as stderr:
            self.assertEqual(main(['--state-dir', str(self.root), '--no-browser']), 2)
        self.assertNotIn('private path', str(stderr.write.call_args_list))

    def test_guided_launch_opens_real_private_ui_with_empty_queue(self):
        process = subprocess.Popen([sys.executable, '-B', '-m', 'arkos_pilot.launcher', '--state-dir', str(self.root), '--no-browser'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines = []
        ready = threading.Event()
        def read():
            for line in process.stdout:
                lines.append(line)
                if line.startswith('http://127.0.0.1:'):
                    ready.set(); return
            ready.set()
        thread = threading.Thread(target=read, daemon=True); thread.start()
        try:
            self.assertTrue(ready.wait(8), 'Launcher did not start')
            urls = [line.strip() for line in lines if line.startswith('http://127.0.0.1:')]
            self.assertTrue(urls, 'Launcher exited without private UI')
            from urllib.parse import urlsplit, parse_qs
            url = urlsplit(urls[0]); key = parse_qs(url.fragment)['key'][0]
            client = http.client.HTTPConnection(url.hostname, url.port, timeout=3)
            client.request('GET', '/api/tasks', headers={'X-Arkos-Key': key})
            response = client.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())['tasks'], [])
            client.close()
            self.assertTrue((self.root / 'queue.sqlite3').is_file())
        finally:
            process.terminate()
            process.communicate(timeout=5)
            thread.join(timeout=1)
