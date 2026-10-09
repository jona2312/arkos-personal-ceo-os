"""Real loopback HTTP + real HermesBridge subprocess, synthetic runner only."""
import concurrent.futures
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from arkos_hermes.bridge import HermesBridge
from arkos_pilot.core import Queue
from arkos_pilot.task_center import TaskCenter

RUNNER = Path(__file__).parent/'fixtures'/'chat_runner.py'


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bridge = HermesBridge(sys.executable, self.root, self.root/'home', runner=RUNNER)
        self.server = TaskCenter(self.root, bridge=self.bridge, chat_mode='synthetic')
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval':.01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def call(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        h = {'X-Arkos-Key':self.server.key,'Origin':self.server.origin,'Content-Type':'application/json'}
        h.update(headers or {})
        conn.request(method, path, json.dumps(data) if data is not None else None, h)
        response = conn.getresponse()
        status, body = response.status, json.loads(response.read())
        conn.close()
        return status, body

    def request(self, rid='request-0001', text='Nota de aceptación', **kwargs):
        return dict(v=1,request_id=rid,messages=[dict(role='user',content=text)],**kwargs)

    def start(self, **kwargs):
        request = self.request(**kwargs)
        code, view = self.call('POST','/api/chat',request)
        self.assertEqual(code,202,view)
        return request

    def done(self, rid='request-0001', timeout=5):
        end = time.monotonic()+timeout
        while time.monotonic()<end:
            code, turn = self.call('GET','/api/chat/'+rid)
            self.assertEqual(code,200)
            if turn['state'] != 'waiting':
                return turn
            time.sleep(.02)
        self.fail('Turn did not finish')

    def test_no_config_has_no_fabricated_response(self):
        self.server.chat.bridge = None
        self.assertFalse(self.call('GET','/api/chat')[1]['configured'])
        self.assertEqual(self.call('POST','/api/chat',self.request())[0],503)
        self.assertEqual(self.call('GET','/api/tasks')[1]['tasks'],[])

    def test_history_and_idempotent_double_submit(self):
        request = self.start()
        self.assertEqual(self.call('POST','/api/chat',request)[0],202)
        turn = self.done()
        self.assertEqual(turn['state'],'ok')
        self.assertEqual(len(self.server.chat.turns),1)
        self.assertNotIn('diagnostics',turn['response'])
        request2 = self.request(rid='request-0002',text='Segundo turno')
        request2['messages'] = request['messages']+[{'role':'assistant','content':turn['response']['reply']}]+request2['messages']
        self.assertEqual(self.call('POST','/api/chat',request2)[0],202)
        self.assertIn('3 mensajes',self.done('request-0002')['response']['reply'])
        request['messages'][0]['content']='Alterado'
        self.assertEqual(self.call('POST','/api/chat',request)[0],409)

    def test_pending_proposal_atomic_dedup_and_no_execution(self):
        self.start(text='<img src=x onerror=alert(1)>')
        turn=self.done()
        pid=turn['response']['proposals'][0]['proposal_id']
        path='/api/chat/request-0001/note'
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda _:self.call('POST',path,{'proposal_id':pid}),range(12)))
        self.assertTrue(all(code==200 for code,_ in results))
        self.assertEqual(len({body['task']['id'] for _,body in results}),1)
        tasks=self.call('GET','/api/tasks')[1]['tasks']
        self.assertEqual(len(tasks),1)
        self.assertEqual(tasks[0]['state'],'awaiting_approval')
        self.assertIsNone(tasks[0]['approval_until'])
        self.assertEqual(list((self.root/'outputs').iterdir()),[])
        queue=Queue(self.root)
        try:
            same=queue.add(tasks[0]['payload'],source_key='chat:request-0001:'+pid)
            self.assertEqual(same['id'],tasks[0]['id'])
        finally:queue.close()
        self.assertEqual(self.call('POST',path,{'proposal_id':pid,'text':'Injected','approved':True})[0],400)
        self.assertEqual(self.call('POST',path,{'proposal_id':'prp_'+'0'*24})[0],400)

    def test_busy_does_not_block_tasks_and_cancel_stops_process(self):
        self.start(text='[wait]')
        self.assertEqual(self.call('POST','/api/chat',self.request(rid='request-0002'))[0],409)
        started=time.monotonic()
        self.assertEqual(self.call('GET','/api/tasks')[0],200)
        self.assertLess(time.monotonic()-started,1)
        for _ in range(100):
            runs=list(self.bridge._active.values())
            if runs and runs[0].process is not None:break
            time.sleep(.01)
        process=runs[0].process
        self.assertIsNotNone(process)
        self.assertEqual(self.call('POST','/api/chat/request-0001/cancel',{})[0],200)
        self.server.chat.turns['request-0001']['thread'].join(3)
        self.assertIsNotNone(process.poll())
        self.assertEqual(self.done()['response']['proposals'],[])
        self.assertEqual(self.call('POST','/api/chat/request-0001/note',{'proposal_id':'prp_'+'0'*24})[0],409)

    def test_cancel_before_bridge_registers_and_close(self):
        original=self.bridge.converse
        gate=threading.Event()
        def delayed(request, cancel_event=None):
            gate.wait(1)
            return original(request,cancel_event=cancel_event)
        with patch.object(self.bridge,'converse',side_effect=delayed):
            self.start(text='[wait]')
            self.call('POST','/api/chat/request-0001/cancel',{})
            gate.set()
            self.server.chat.close()
        self.assertEqual(self.done()['state'],'cancelled')
        self.assertFalse(self.bridge._active)
        self.assertFalse(self.server.chat.turns['request-0001']['thread'].is_alive())

    def test_error_invalid_and_timeout_never_offer_proposals(self):
        for i,text in enumerate(('[error]','[invalid]','[timeout]')):
            rid='request-'+str(i).zfill(4)
            self.start(rid=rid,text=text,timeout_s=10)
            turn=self.done(rid,timeout=13)
            self.assertEqual(turn['state'],'timeout' if text=='[timeout]' else 'error')
            self.assertEqual(turn['response']['proposals'],[])
            self.assertEqual(turn['response']['reply'],'')

    def test_auth_origin_host_roles_limits_and_session_budget(self):
        for headers,code in [({'X-Arkos-Key':''},401),({'Origin':'http://attacker.test'},403),
                             ({'Host':'attacker.test'},403)]:
            self.assertEqual(self.call('POST','/api/chat',self.request(),headers)[0],code)
            self.assertEqual(self.call('GET','/api/chat',headers=headers)[0],code)
        request=self.request()
        request['messages'][0]['role']='system'
        self.assertEqual(self.call('POST','/api/chat',request)[0],400)
        self.assertEqual(self.call('POST','/api/chat',self.request(text='x'*8001))[0],400)
        self.assertEqual(self.call('POST','/api/chat',self.request(text='x'*210000))[0],400)
        with patch('arkos_pilot.chat.MAX_TURNS',0):
            self.assertEqual(self.call('POST','/api/chat',self.request())[0],429)
        self.assertFalse(self.bridge._active)

    def test_close_terminates_active_runner(self):
        self.start(text='[wait]')
        for _ in range(100):
            runs=list(self.bridge._active.values())
            if runs and runs[0].process is not None:break
            time.sleep(.01)
        process=runs[0].process
        self.server.chat.close()
        self.assertIsNotNone(process.poll())
        self.assertFalse(self.server.chat.turns['request-0001']['thread'].is_alive())

    def test_server_revalidates_held_content_and_queue_limit(self):
        from arkos_hermes import contract as c
        self.start()
        self.done()
        proposal=self.server.chat.turns['request-0001']['response']['proposals'][0]
        for text in ('', ' ', 'bad\x00content', 'x'*(c.MAX_NOTE_CHARS+1)):
            proposal['text']=text
            proposal['proposal_id']='prp_'+c.proposal_digest(proposal)[:24]
            self.assertEqual(self.call('POST','/api/chat/request-0001/note',
                                      {'proposal_id':proposal['proposal_id']})[0],400)
        self.assertEqual(self.call('GET','/api/tasks')[1]['tasks'],[])

    def test_wrong_session_cannot_read_cancel_or_create(self):
        self.start()
        pid=self.done()['response']['proposals'][0]['proposal_id']
        headers={'X-Arkos-Key':'another-synthetic-session'}
        for method,path,body in [('GET','/api/chat/request-0001',None),
                                 ('POST','/api/chat/request-0001/cancel',{}),
                                 ('POST','/api/chat/request-0001/note',{'proposal_id':pid})]:
            self.assertEqual(self.call(method,path,body,headers)[0],401)
        self.assertEqual(self.call('GET','/api/tasks')[1]['tasks'],[])
