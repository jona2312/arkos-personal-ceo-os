"""Exercise the committed package, not imports from the source checkout."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class WindowsPackageTests(unittest.TestCase):
    def test_reproducible_allowlist_integrity_and_extracted_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archives = []
            for directory in ('one', 'two'):
                result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/Build-ArkosPackage.py'),
                                         '--output', str(root / directory)], cwd=root,
                                        capture_output=True, text=True, check=True)
                archives.append(Path(result.stdout.strip()))
            self.assertEqual(archives[0].read_bytes(), archives[1].read_bytes())
            self.assertEqual(archives[0].with_suffix('.zip.sha256').read_text().split()[0],
                             hashlib.sha256(archives[0].read_bytes()).hexdigest())
            extracted = root / 'paquete con espacios y ñ'
            with zipfile.ZipFile(archives[0]) as z:
                manifest = json.loads(z.read('MANIFEST.json'))
                sha = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).decode().strip()
                self.assertEqual(manifest['source_commit'], sha)
                self.assertFalse(manifest['cloud_enabled'])
                spec = json.loads(subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{sha}:packaging/windows-pilot.json']))
                self.assertEqual(set(z.namelist()), set(spec['files']) | {'MANIFEST.json', 'SHA256SUMS.txt'})
                for item in manifest['files']:
                    content = z.read(item['path'])
                    self.assertEqual(item['bytes'], len(content))
                    self.assertEqual(item['sha256'], hashlib.sha256(content).hexdigest())
                for line in z.read('SHA256SUMS.txt').decode().splitlines():
                    digest, name = line.split('  ', 1)
                    self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(), digest)
                self.assertFalse(any(n.endswith(('.sqlite3', '.env', '.gguf')) for n in z.namelist()))
                z.extractall(extracted)
            # Tests copied alone, so imports and subprocesses resolve ONLY to extracted code.
            test_dir = extracted / 'acceptance_tests'
            test_dir.mkdir()
            for name in ('test_launcher.py', 'test_task_center.py', 'test_chat_center.py'):
                source = ROOT / 'tests' / name
                if not source.is_file():
                    self.fail(f'Missing required acceptance suite: {name}')
                (test_dir / name).write_bytes(source.read_bytes())
            (test_dir / 'fixtures').mkdir()
            (test_dir / 'fixtures/chat_runner.py').write_bytes((ROOT / 'tests/fixtures/chat_runner.py').read_bytes())
            result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', str(test_dir), '-v'],
                                    cwd=extracted, capture_output=True, text=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
