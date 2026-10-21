"""One resident offline worker, bounded requests, explicit lease and cancellation.

No Hermes configuration, credential access, downloads, queue writes or audio files.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time

from arkos_hermes.bridge import PASSTHROUGH_ENV
from .chat import ChatError
from .dictation import Dictation, decode_audio

ID = re.compile(r'^voice-[a-f0-9-]{36}$')


class Voice:
    def __init__(self, python, model, piper, *, timeout=90):
        # Reuse the installed-runtime checks; editable dictation remains independent.
        checked = Dictation(python, model)
        self.python, self.model = checked.python, checked.model
        self.piper = Path(piper).resolve()
        if not self.piper.is_file() or not Path(str(self.piper) + '.json').is_file():
            raise ValueError('La voz Piper local y su JSON deben existir; no se descargan.')
        self.timeout = timeout
        self.lock = threading.Lock()
        self.process = None
        self.owner = None
        self.busy = False
        self.closed = False
        self.receipts = set()
        self.cancelled = set()
        self.last_used = time.monotonic()
        self.reaper_stop = threading.Event()
        self.reaper = threading.Thread(target=self._reap, daemon=True)
        self.reaper.start()

    def _reap(self):
        while not self.reaper_stop.wait(10):
            with self.lock:
                if not self.busy and self.process and time.monotonic() - self.last_used > 120:
                    self._kill()
                    self.owner = None

    def _kill(self):
        process, self.process = self.process, None
        if process:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout):
                pipe.close()

    def call(self, op, data):
        fields = {'session_id', 'request_id'} | ({'audio'} if op == 'transcribe' else {'text'} if op == 'speak' else set())
        if op not in ('warm', 'transcribe', 'speak', 'cancel') or set(data) != fields:
            raise ValueError('Pedido de voz inválido.')
        if any(not isinstance(data[k], str) or not ID.fullmatch(data[k]) for k in ('session_id', 'request_id')):
            raise ValueError('Identificador de voz inválido.')
        if op == 'transcribe':
            decode_audio({'request_id': 'dict-' + data['request_id'][6:], 'audio': data['audio']})
        if op == 'speak' and (not isinstance(data['text'], str) or not data['text'].strip() or
                             len(data['text']) > 1000 or '\x00' in data['text']):
            raise ValueError('La frase debe tener entre 1 y 1000 caracteres.')
        with self.lock:
            if self.closed:
                raise ChatError('Voz cerrada.', 503)
            if op == 'cancel':
                if len(self.cancelled) >= 1024:
                    raise ChatError('Límite de sesiones de voz alcanzado.', 429)
                self.cancelled.add(data['session_id'])
                if self.owner == data['session_id']:
                    self.owner = None
                    self._kill()
                return {'cancelled': True}
            if data['session_id'] in self.cancelled:
                raise ChatError('Sesión de voz cancelada.', 409)
            if self.busy or (self.owner and self.owner != data['session_id']):
                raise ChatError('Otra sesión está usando la voz local.', 409)
            if data['request_id'] in self.receipts:
                raise ChatError('Pedido de voz repetido.', 409)
            if len(self.receipts) >= 1024:
                raise ChatError('Límite de voz alcanzado. Reiniciá la prueba.', 429)
            self.receipts.add(data['request_id'])
            self.owner = data['session_id']
            if not self.process:
                self.process = subprocess.Popen(
                    [str(self.python), '-I', '-B', str(Path(__file__).with_name('voice_runner.py')),
                     str(self.model), str(self.piper)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, env={k: os.environ[k] for k in PASSTHROUGH_ENV if k in os.environ},
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            process = self.process
            self.busy = True
        done, output = threading.Event(), []
        def exchange():
            try:
                payload = {'op': op, **{k: data[k] for k in ('audio', 'text') if k in data}}
                process.stdin.write(json.dumps(payload).encode() + b'\n')
                process.stdin.flush()
                output.append(process.stdout.readline(10_700_000))
            except (OSError, ValueError):
                pass
            finally:
                done.set()
        thread = threading.Thread(target=exchange, daemon=True)
        started = time.perf_counter()
        thread.start()
        try:
            if not done.wait(self.timeout):
                raise ChatError('La voz local agotó el tiempo.', 504)
            with self.lock:
                if self.process is not process or self.owner != data['session_id']:
                    raise ChatError('Voz cancelada.', 409)
            if not output or not output[0].endswith(b'\n') or len(output[0]) >= 10_700_000:
                raise ChatError('Falló el componente local de voz.', 503)
            result = json.loads(output[0])
            if op == 'transcribe' and (not isinstance(result.get('text'), str) or len(result['text']) > 4000):
                raise ValueError('Transcripción inválida.')
            result.update(elapsed_ms=round((time.perf_counter()-started)*1000), processing='local', audio_saved=False)
            return result
        except Exception:
            with self.lock:
                if self.process is process:
                    self._kill()
                    self.owner = None
            raise
        finally:
            with self.lock:
                self.busy = False
                self.last_used = time.monotonic()

    def close(self):
        self.reaper_stop.set()
        with self.lock:
            self.closed = True
            self.owner = None
            self._kill()
        self.reaper.join(timeout=2)
