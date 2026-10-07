"""Regression checks for local-only benchmarking and preserving profile context."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('voice_trial', ROOT / 'scripts/Test-HermesVoicePipeline.py')
voice_trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(voice_trial)


class VoiceEndpointTests(unittest.TestCase):
    def test_public_or_credentialed_endpoints_never_receive_requests(self):
        for value in ('https://api.example.com/v1', 'http://10.0.0.1/v1',
                      'http://127.0.0.1.example.com/v1', 'http://user:secret@127.0.0.1/v1',
                      'http://127.0.0.1/v1?key=secret', 'file:///tmp/model'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                voice_trial.local_url(value)

    def test_explicit_loopback_endpoint_is_accepted(self):
        self.assertEqual(voice_trial.local_url('http://127.0.0.1:18434/v1/'),
                         'http://127.0.0.1:18434/v1')

    def test_local_redirect_cannot_forward_internal_authentication(self):
        with self.assertRaises(ValueError):
            voice_trial.NoRedirects().redirect_request(None, None, 302, '', {}, 'https://example.com')


class ContextSyncTests(unittest.TestCase):
    def run_sync(self, profile, workspace, apply=False):
        args = [sys.executable, str(ROOT / 'scripts/Sync-ArkosHermesContext.py'),
                '--profile-home', str(profile), '--workspace', str(workspace)]
        if apply:
            args.append('--apply')
        return subprocess.run(args, capture_output=True, text=True, encoding='utf-8')

    def test_preview_backup_and_idempotence(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            profile = base / 'arkos-pilot'
            workspace = base / 'trial'
            profile.mkdir()
            workspace.mkdir()
            original = b'User-owned context\r\nDo not discard.\r\n'
            (profile / 'SOUL.md').write_bytes(original)
            (profile / 'config.yaml').write_text('example: unchanged\n')
            preview = self.run_sync(profile, workspace)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertEqual((profile / 'SOUL.md').read_bytes(), original)
            result = self.run_sync(profile, workspace, True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(Path(report['backup']).read_bytes(), original)
            self.assertIn(workspace.as_posix(), (profile / 'SOUL.md').read_text(encoding='utf-8'))
            second = self.run_sync(profile, workspace, True)
            self.assertFalse(json.loads(second.stdout)['changed'])
            self.assertEqual(len(list(profile.glob('SOUL.before-*.md'))), 1)
            self.assertEqual((profile / 'config.yaml').read_text(), 'example: unchanged\n')

    def test_unrelated_profile_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            profile = base / 'default'
            workspace = base / 'trial'
            profile.mkdir()
            workspace.mkdir()
            (profile / 'config.yaml').write_text('{}')
            (profile / 'SOUL.md').write_text('untouched')
            self.assertNotEqual(self.run_sync(profile, workspace, True).returncode, 0)
            self.assertEqual((profile / 'SOUL.md').read_text(), 'untouched')


if __name__ == '__main__':
    unittest.main()
