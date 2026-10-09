"""Bounded asynchronous conversation. No tools, approvals or task execution."""
import copy
import re
import threading

from arkos_hermes import contract as c
from .core import Queue, validate

REQUEST_ID = re.compile(r'[A-Za-z0-9_.:-]{8,64}')
PROPOSAL_ID = re.compile(r'prp_[0-9a-f]{24}')
MAX_TURNS = 64  # reject when full: never evict an idempotency receipt mid-session


class ChatError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


class Conversations:
    def __init__(self, root, bridge=None, mode='hermes'):
        self.root, self.bridge = root, bridge
        self.mode = mode if bridge else 'unconfigured'
        self.lock = threading.RLock()
        self.turns = {}
        self.active = None
        self.closed = False

    def status(self):
        with self.lock:
            return dict(configured=self.bridge is not None, mode=self.mode,
                        active_request_id=self.active, remaining=MAX_TURNS-len(self.turns))

    def _view(self, turn):
        response = turn['response']
        return copy.deepcopy(dict(request=turn['request'], state=turn['state'],
                                  response=response, created_tasks=turn['created_tasks']))

    def get(self, request_id):
        with self.lock:
            if request_id not in self.turns:
                raise ChatError('Turno no disponible en esta sesión.', 404)
            return self._view(self.turns[request_id])

    def start(self, request):
        request = c.validate_request(request)
        rid = request['request_id']
        if not REQUEST_ID.fullmatch(rid):
            raise ValueError('Identificador de turno inválido.')
        with self.lock:
            if self.closed or self.bridge is None:
                raise ChatError('Hermes por conectar.', 503)
            if rid in self.turns:
                if self.turns[rid]['request'] != request:
                    raise ChatError('Este identificador ya corresponde a otro pedido.')
                return self._view(self.turns[rid])
            if self.active:
                raise ChatError('Hay una conversación esperando respuesta. Cancelala o esperá.')
            if len(self.turns) >= MAX_TURNS:
                raise ChatError('Se alcanzó el límite de esta sesión. Reiniciá el servidor.', 429)
            turn = dict(request=request, state='waiting', response=None,
                        cancel=threading.Event(), created_tasks={})
            self.turns[rid] = turn
            self.active = rid
            thread = threading.Thread(target=self._work, args=(rid, turn), daemon=True)
            turn['thread'] = thread
            thread.start()
            return self._view(turn)

    def _work(self, rid, turn):
        try:
            result = self.bridge.converse(turn['request'], cancel_event=turn['cancel'])
            result = c.validate_response(result, rid)
            # Browser receives display fields only, never runtime diagnostics/paths.
            result = {k: result[k] for k in ('status', 'reply', 'proposals')}
            if result['status'] != 'ok':
                result['error'] = 'El turno no se completó. No se creó ninguna tarea.'
        except Exception:
            result = dict(status='error', reply='', proposals=[],
                          error='No se pudo obtener una respuesta válida de Hermes.')
        with self.lock:
            if turn['cancel'].is_set():
                result = dict(status='cancelled', reply='', proposals=[])
            turn['response'] = result
            turn['state'] = result['status']
            self.active = None

    def cancel(self, rid):
        with self.lock:
            if rid not in self.turns:
                raise ChatError('Turno no disponible.', 404)
            turn = self.turns[rid]
            if turn['state'] == 'waiting':
                turn['cancel'].set()
                turn['state'] = 'cancelled'
                turn['response'] = dict(status='cancelled', reply='', proposals=[])
            return self._view(turn)

    def create_note(self, rid, proposal_id):
        with self.lock:
            turn = self.turns.get(rid)
            if not turn or turn['state'] != 'ok' or turn['cancel'].is_set():
                raise ChatError('Solo una respuesta válida permite crear una nota.')
            proposals = turn['response']['proposals']
            proposal = next((p for p in proposals if p['proposal_id'] == proposal_id), None)
            if not proposal or not PROPOSAL_ID.fullmatch(proposal_id):
                raise ValueError('Propuesta no disponible.')
            # Trust only a server-held, revalidated proposal, never browser text.
            c.validate_response(c.response(rid, 'ok', proposals=[proposal]), rid)
            c._text(proposal['text'], c.MAX_NOTE_CHARS, 'Nota')
            payload = dict(action='note', text=proposal['text'])
            validate(payload)
            queue = Queue(self.root)
            try:
                task = queue.add(payload, source_key='chat:'+rid+':'+proposal_id)
            finally:
                queue.close()
            turn['created_tasks'][proposal_id] = task['id']
            return task

    def close(self):
        with self.lock:
            self.closed = True
            turns = list(self.turns.values())
            for turn in turns:
                turn['cancel'].set()
        for turn in turns:
            turn['thread'].join(timeout=15)
