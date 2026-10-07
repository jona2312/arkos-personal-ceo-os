import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from arkos_pilot.core import Queue
from arkos_pilot.task_center import TaskCenter


class TaskCenterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = TaskCenter(self.temp.name)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        # Tests wait for completion; don't delete state beneath a worker.
        deadline = time.monotonic() + 3
        while self.server.worker_lock.locked() and time.monotonic() < deadline:
            time.sleep(.01)
        self.temp.cleanup()

    def request(self, method, path, data=None, headers=None, key=True):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        h = {'Origin': self.server.origin}
        if key: h['X-Arkos-Key'] = self.server.key
        if data is not None: h['Content-Type'] = 'application/json'
        if headers: h.update(headers)
        try:
            client.request(method, path, body=json.dumps(data) if data is not None else None, headers=h)
            response = client.getresponse()
            content = response.read()
            return response.status, content, dict(response.getheaders())
        finally:
            client.close()

    def json(self, method, path, data=None):
        code, content, _ = self.request(method, path, data)
        return code, json.loads(content)

    def note(self, text='Prueba de revisión'):
        code, body = self.json('POST','/api/tasks',{'action':'note','text':text})
        self.assertEqual(code,201)
        return body['task']

    def approve(self, task):
        code, _ = self.json('POST',f"/api/tasks/{task['id']}/approve",{'fingerprint':task['fingerprint']})
        self.assertEqual(code,200)

    def wait_for(self, task_id, expected='completed'):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            with QueueContext(self.temp.name) as queue:
                task = queue.get(task_id)
            if task['state'] == expected: return task
            time.sleep(.01)
        self.fail(f"Task did not reach {expected}: {task}")

    def test_http_note_review_execute_artifact_and_persistence(self):
        task = self.note('Idea <script>alert(1)</script>\nmañana')
        code, _ = self.json('POST',f"/api/tasks/{task['id']}/run",{})
        self.assertEqual(code,400)
        self.approve(task)
        self.assertEqual(self.json('POST',f"/api/tasks/{task['id']}/run",{})[0],202)
        self.wait_for(task['id'])
        code, content, headers = self.request('GET',f"/api/tasks/{task['id']}/artifact")
        self.assertEqual(code,200)
        self.assertIn('mañana',content.decode())
        self.assertTrue(headers['Content-Type'].startswith('text/plain'))
        self.assertIn('attachment',headers['Content-Disposition'])
        self.assertEqual(self.json('POST',f"/api/tasks/{task['id']}/run",{})[0],400)
        # A second server opens the same SQLite state; no in-memory task copy.
        other = TaskCenter(self.temp.name)
        try:
            with QueueContext(other.root) as q:
                self.assertEqual(q.get(task['id'])['state'],'completed')
                self.assertEqual(len(list(q.output.iterdir())),1)
        finally: other.server_close()

    def test_selected_task_does_not_execute_another_queued_task(self):
        first, second = self.note('Primera'), self.note('Elegida')
        self.approve(first); self.approve(second)
        self.json('POST',f"/api/tasks/{second['id']}/run",{})
        self.wait_for(second['id'])
        with QueueContext(self.temp.name) as q:
            self.assertEqual(q.get(first['id'])['state'],'queued')

    def test_cancel_and_fingerprint_mismatch(self):
        task = self.note()
        self.assertEqual(self.json('POST',f"/api/tasks/{task['id']}/approve",{'fingerprint':'wrong'})[0],400)
        self.assertEqual(self.json('POST',f"/api/tasks/{task['id']}/cancel",{})[0],200)
        self.assertEqual(self.json('POST',f"/api/tasks/{task['id']}/approve",{'fingerprint':task['fingerprint']})[0],400)

    def test_expired_approval_blocks_execution(self):
        task = self.note(); self.approve(task)
        with QueueContext(self.temp.name) as q:
            q.db.execute('UPDATE tasks SET approval_until=0 WHERE id=?',(task['id'],));q.db.commit()
        self.json('POST',f"/api/tasks/{task['id']}/run",{})
        self.wait_for(task['id'],'blocked')
        self.assertEqual(list((Path(self.temp.name)/'outputs').iterdir()),[])

    def test_private_routes_require_token(self):
        for path in ['/api/tasks','/api/status','/api/tasks/'+'a'*32+'/artifact']:
            self.assertEqual(self.request('GET',path,key=False)[0],401)
        self.assertEqual(self.request('POST','/api/tasks',{'action':'note','text':'bad'},key=False)[0],401)

    def test_host_origin_and_cross_site_requests_are_blocked(self):
        for headers in [{'Host':'attacker.example'}, {'Origin':'https://attacker.example'}, {'Sec-Fetch-Site':'cross-site'}]:
            self.assertEqual(self.request('GET','/api/tasks',headers=headers)[0],403)
            self.assertEqual(self.request('POST','/api/tasks',{'action':'note','text':'bad'},headers=headers)[0],403)
        self.assertEqual(self.request('POST','/api/tasks',{},headers={'Origin':''})[0],403)
        self.assertEqual(self.json('GET','/api/tasks')[1]['tasks'],[])

    def test_static_assets_have_no_secrets_and_no_path_traversal(self):
        for path in ['/','/app.js','/style.css','/mark.svg']:
            code,content,headers=self.request('GET',path,key=False)
            self.assertEqual(code,200)
            self.assertNotIn(self.server.key.encode(),content)
            self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
            self.assertEqual(headers['Cache-Control'],'no-store')
        for path in ['/../core.py','/core.py','/api/tasks/../../artifact']:
            self.assertNotEqual(self.request('GET',path)[0],200)

    def test_artifact_cannot_serve_external_result_path(self):
        task=self.note()
        with QueueContext(self.temp.name) as q:
            target=q.output/(task['id']+'.md');target.write_text('safe')
            q.db.execute("UPDATE tasks SET state='completed', result=? WHERE id=?",('/etc/passwd',task['id']));q.db.commit()
        self.assertEqual(self.request('GET',f"/api/tasks/{task['id']}/artifact")[0],400)

    def test_unsupported_actions_and_invalid_proposals(self):
        for data in [{'action':'shell','command':'echo bad'},{'action':'note','text':''}, {'action':'clip','source':'relative.mp4','start':0,'duration':1}, []]:
            self.assertEqual(self.json('POST','/api/tasks',data)[0],400)
        self.assertEqual(self.json('POST','/api/propose',{'goal':''})[0],400)
        code,result=self.json('POST','/api/propose',{'goal':'Quiero recortar un video'})
        self.assertEqual(code,200);self.assertIn('reglas',result['scope'])
        self.assertEqual(self.json('GET','/api/tasks')[1]['tasks'],[])

    def test_only_one_web_worker_and_cancel_before_claim(self):
        task=self.note();self.approve(task)
        self.server.worker_lock.acquire()
        try: self.assertEqual(self.json('POST',f"/api/tasks/{task['id']}/run",{})[0],400)
        finally: self.server.worker_lock.release()
        self.json('POST',f"/api/tasks/{task['id']}/cancel",{})
        self.assertEqual(self.json('POST',f"/api/tasks/{task['id']}/run",{})[0],400)

    def test_clip_prepare_hashes_source_then_detects_change(self):
        source=Path(self.temp.name)/'source.mp4';source.write_bytes(b'original')
        code,body=self.json('POST','/api/tasks',{'action':'clip','source':str(source),'start':0,'duration':1})
        self.assertEqual(code,201)
        task=body['task'];self.assertEqual(len(task['payload']['source_sha256']),64)
        self.approve(task);source.write_bytes(b'changed')
        with patch('arkos_pilot.core.shutil.which',return_value='ffmpeg'):
            self.json('POST',f"/api/tasks/{task['id']}/run",{})
            self.wait_for(task['id'],'blocked')


class QueueContext:
    def __init__(self,root): self.queue=Queue(root)
    def __enter__(self): return self.queue
    def __exit__(self,*args): self.queue.close()
