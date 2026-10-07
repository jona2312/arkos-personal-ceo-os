import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from arkos_pilot.catalog import propose
from arkos_pilot.core import Queue, clip_payload, validate


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.queue = Queue(self.temp.name)

    def tearDown(self):
        self.queue.close()
        self.temp.cleanup()

    def note(self):
        return self.queue.add({"action": "note", "text": "Preparar propuesta para mañana"})

    def approve(self, task):
        return self.queue.approve(task["id"], task["fingerprint"])

    def test_unapproved_action_does_not_execute(self):
        self.note()
        self.assertIsNone(self.queue.run_next())
        self.assertEqual(list(self.queue.output.iterdir()), [])

    def test_queue_survives_restart_and_executes_once(self):
        task = self.approve(self.note())
        self.queue.close()
        self.queue = Queue(self.temp.name)
        result = self.queue.run_next()
        self.assertEqual(result["state"], "completed")
        self.assertIn("mañana", Path(result["result"]).read_text(encoding="utf-8"))
        self.assertIsNone(self.queue.run_next())
        self.assertEqual(self.queue.get(task["id"])["state"], "completed")

    def test_approval_bound_to_task(self):
        task = self.note()
        with self.assertRaises(ValueError): self.queue.approve(task["id"], "wrong")
        with self.assertRaises(ValueError): self.queue.approve("unknown", task["fingerprint"])
        self.assertEqual(self.queue.get(task["id"])["state"], "awaiting_approval")

    def test_expired_approval_blocks_execution(self):
        task = self.approve(self.note())
        self.queue.db.execute("UPDATE tasks SET approval_until=0 WHERE id=?", (task["id"],))
        self.queue.db.commit()
        self.assertEqual(self.queue.run_next()["state"], "blocked")

    def test_modified_payload_blocks_execution(self):
        task = self.approve(self.note())
        self.queue.db.execute("UPDATE tasks SET payload=? WHERE id=?", (json.dumps({"action": "note", "text": "Changed"}), task["id"]))
        self.queue.db.commit()
        self.assertEqual(self.queue.run_next()["state"], "blocked")

    def test_cancelled_task_does_not_execute(self):
        task = self.approve(self.note())
        self.queue.cancel(task["id"])
        self.assertIsNone(self.queue.run_next())
        with self.assertRaises(ValueError): self.approve(task)

    def test_second_worker_cannot_repeat_task(self):
        self.approve(self.note())
        other = Queue(self.temp.name)
        try:
            self.queue.run_next()
            self.assertIsNone(other.run_next())
        finally: other.close()

    def test_recovery_requires_new_approval(self):
        task = self.approve(self.note())
        self.queue.db.execute("UPDATE tasks SET state='running' WHERE id=?", (task["id"],))
        self.queue.db.commit()
        self.queue.recover()
        self.assertEqual(self.queue.get(task["id"])["state"], "blocked")
        self.assertIsNone(self.queue.run_next())

    def test_invalid_actions_and_times(self):
        for payload in ({"action": "shell", "command": "anything"}, {"action": "note", "text": ""}):
            with self.assertRaises(ValueError): self.queue.add(payload)
        for hours in (0, -1, 25):
            with self.assertRaises(ValueError): self.queue.approve(self.note()["id"], "wrong", hours)

    def test_proactive_proposal(self):
        result = propose("Quiero recortar un vídeo")
        self.assertEqual(result["tools"][0]["id"], "ffmpeg")
        self.assertIn("duración", result["next_step"])

    def test_changed_video_is_blocked(self):
        source = Path(self.temp.name) / "source.mp4"
        source.write_bytes(b"original")
        task = self.approve(self.queue.add(clip_payload(source, 0, 1)))
        source.write_bytes(b"changed")
        with patch("arkos_pilot.core.shutil.which", return_value="ffmpeg"):
            self.assertEqual(self.queue.run_next()["state"], "blocked")

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg not installed")
    def test_real_video_cut_preserves_original(self):
        source = Path(self.temp.name) / "source.mp4"
        subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=2", "-c:v", "mpeg4", str(source)], check=True)
        payload = clip_payload(source, 0.5, 1)
        task = self.approve(self.queue.add(payload))
        result = self.queue.run_next()
        self.assertEqual(result["state"], "completed", result["result"])
        self.assertTrue(Path(result["result"]).is_file())
        self.assertEqual(clip_payload(source, 0.5, 1), payload)


if __name__ == "__main__": unittest.main()
