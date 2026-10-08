"""Regression: the CLI must not crash on a cp1252 console (default on Windows)."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
    return subprocess.run([sys.executable, "-m", "arkos_relay", *args], cwd=ROOT, env=env, capture_output=True, timeout=60)


class Cp1252ConsoleTests(unittest.TestCase):
    def test_help_on_cp1252(self):
        result = run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr.decode("cp1252", "replace"))
        self.assertIn("arkos_relay", result.stdout.decode("cp1252"))

    def test_status_with_characters_outside_cp1252(self):
        # Synthetic agent state whose text includes characters cp1252 cannot encode.
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp)
            config = {"server": "https://relay.invalid", "device_id": "dev_" + "0" * 32,
                      "device_name": "PC → prueba 🎬", "roots": {}}
            (state / "agent.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            result = run_cli("agent", "--state-dir", str(state), "status")
            self.assertEqual(result.returncode, 0, result.stderr.decode("cp1252", "replace"))
            status = json.loads(result.stdout.decode("cp1252"))  # still valid JSON
            self.assertEqual(status["config"]["device_name"], "PC → prueba 🎬")  # nothing lost

    def test_messages_outside_cp1252_do_not_crash(self):
        code = "from arkos_relay.__main__ import safe_console; safe_console(); print('cola → PC \U0001f3ac')"
        env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr.decode("cp1252", "replace"))
        self.assertEqual(result.stdout.decode("cp1252").strip(), r"cola \u2192 PC \U0001f3ac")


if __name__ == "__main__":
    unittest.main()
