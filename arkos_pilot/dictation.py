"""Opt-in offline dictation. Audio lives in memory; no queue or model tools."""
import base64
import io
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import wave

from .chat import ChatError
from arkos_hermes.bridge import PASSTHROUGH_ENV

MAX_SAMPLES = 16000 * 30
MAX_AUDIO = MAX_SAMPLES * 2 + 44


def decode_audio(data):
    if not isinstance(data, dict) or set(data) != {'request_id', 'audio'}:
        raise ValueError('Pedido de dictado inválido.')
    if not isinstance(data['request_id'], str) or not re.fullmatch(r'dict-[a-f0-9-]{36}', data['request_id']):
        raise ValueError('Identificador de dictado inválido.')
    encoded = data['audio']
    if not isinstance(encoded, str) or len(encoded) > (MAX_AUDIO + 2) // 3 * 4:
        raise ValueError('Dictado demasiado largo: máximo 30 segundos.')
    try:
        audio = base64.b64decode(encoded, validate=True)
        with wave.open(io.BytesIO(audio), 'rb') as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 16000, 'NONE'):
                raise ValueError()
            count = wav.getnframes()
            if not 1600 <= count <= MAX_SAMPLES or len(wav.readframes(count)) != count * 2:
                raise ValueError()
    except Exception:
        raise ValueError('Audio inválido: WAV mono PCM16, 16 kHz, entre 0,1 y 30 segundos.') from None
    return audio


class Dictation:
    def __init__(self, python, model, *, timeout=90):
        self.python, self.model = Path(python).resolve(), Path(model).resolve()
        if not self.python.is_file() or not all((self.model / name).is_file() for name in (
                'model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt')):
            raise ValueError('Dictado requiere Python y modelo faster-whisper locales completos; no se descargan.')
        self.timeout = timeout
        self.lock = threading.Lock()
        self.active = None
        self.closed = False
        self.seen = set()  # bounded receipts, including cancel-before-start

    def transcribe(self, data):
        audio = decode_audio(data)
        with self.lock:
            if self.closed:
                raise ChatError('Dictado cerrado.', 503)
            if self.active:
                raise ChatError('Ya hay un dictado en proceso.', 409)
            if data['request_id'] in self.seen:
                raise ChatError('Este dictado ya fue recibido o cancelado.', 409)
            if len(self.seen) >= 128:
                raise ChatError('Límite de dictados de esta sesión alcanzado.', 429)
            self.seen.add(data['request_id'])
            # Fixed executable and runner, never paths or commands supplied by a browser.
            process = subprocess.Popen(
                [str(self.python), '-I', '-B', str(Path(__file__).with_name('dictation_runner.py')), str(self.model)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env={k: os.environ[k] for k in PASSTHROUGH_ENV if k in os.environ},
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            job = {'id': data['request_id'], 'process': process, 'cancelled': False}
            self.active = job
        try:
            try:
                output, _ = process.communicate(audio, timeout=self.timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise ChatError('El dictado agotó el tiempo. Probá una frase más corta.', 504) from None
            with self.lock:
                if job['cancelled']:
                    raise ChatError('Dictado cancelado.', 409)
            if process.returncode:
                raise ChatError('No se pudo transcribir localmente. Revisá el runtime de dictado.', 503)
            try:
                text = json.loads(output)['text']
                if not isinstance(text, str) or len(text) > 4000 or '\x00' in text:
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise ChatError('Respuesta del dictado inválida.', 503) from None
            return {'text': text, 'processing': 'local', 'audio_saved': False}
        finally:
            with self.lock:
                if self.active is job:
                    self.active = None

    def cancel(self, request_id):
        if not isinstance(request_id, str) or not re.fullmatch(r'dict-[a-f0-9-]{36}', request_id):
            raise ValueError('Identificador de dictado inválido.')
        with self.lock:
            if request_id not in self.seen:
                if len(self.seen) >= 128:
                    raise ChatError('Límite de dictados de esta sesión alcanzado.', 429)
                self.seen.add(request_id)
            if self.active and self.active['id'] == request_id:
                self.active['cancelled'] = True
                if self.active['process'].poll() is None:
                    self.active['process'].kill()
        return {'cancelled': True}

    def close(self):
        with self.lock:
            self.closed = True
            job = self.active
            if job:
                job['cancelled'] = True
                if job['process'].poll() is None:
                    job['process'].kill()
        if job:
            job['process'].wait(timeout=5)
