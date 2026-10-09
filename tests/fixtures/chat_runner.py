"""Explicit synthetic acceptance runner. Never imports Hermes or contacts a model."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from arkos_hermes import contract as c

request = c.validate_request(json.load(sys.stdin))
text = request['messages'][-1]['content']
if text in ('[wait]', '[timeout]'):
    time.sleep(30)
if text == '[error]':
    result = c.response(request['request_id'], 'error', error=('model_error', 'Synthetic failure'))
elif text == '[invalid]':
    result = c.response(request['request_id'], 'error', error=('model_error', 'Synthetic failure'))
    result['reply'] = 'Must never be displayed'
    result['proposals'] = [{'type': 'note', 'text': 'Must never be used'}]
else:
    time.sleep(.3)
    note = {'type':'note','title':'Nota sintética revisable','text':text}
    fence = chr(96)*3
    _, proposals, _ = c.parse_reply(fence+'arkos-proposal\n'+json.dumps(note)+'\n'+fence)
    result = c.response(request['request_id'], 'ok',
                        reply='PRUEBA SINTÉTICA. Recibí '+str(len(request['messages']))+' mensajes. Propuesta para revisar: '+text,
                        proposals=proposals)
print(json.dumps(result, ensure_ascii=True))
