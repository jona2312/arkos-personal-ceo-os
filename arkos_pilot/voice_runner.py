"""Resident, offline voice worker. JSON lines in/out; audio only in memory."""
import base64
import io
import json
import os
import sys
import time
import wave


def main():
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    def offline(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo', 'socket.bind'):
            raise RuntimeError('Voice is offline')
    sys.addaudithook(offline)
    import numpy as np
    from faster_whisper import WhisperModel
    from piper import PiperVoice
    stt = WhisperModel(sys.argv[1], device='cpu', compute_type='int8', cpu_threads=4, local_files_only=True)
    tts = PiperVoice.load(sys.argv[2], use_cuda=False)
    while True:
        line = sys.stdin.buffer.readline(1_282_000)
        if not line:
            return
        if len(line) >= 1_282_000 or not line.endswith(b'\n'):
            raise ValueError('Frame limit')
        request = json.loads(line)
        started = time.perf_counter()
        op = request['op']
        if op == 'warm':
            result = {'ready': True}
        elif op == 'transcribe':
            raw = base64.b64decode(request['audio'], validate=True)
            with wave.open(io.BytesIO(raw), 'rb') as source:
                if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
                    raise ValueError('Audio format')
                frames = source.readframes(480001)
            audio = np.frombuffer(frames, dtype='<i2').astype(np.float32) / 32768
            segments, _ = stt.transcribe(audio, language='es', beam_size=1, vad_filter=False,
                                        condition_on_previous_text=False)
            result = {'text': ' '.join(s.text.strip() for s in segments).strip()}
        elif op == 'speak':
            buf = io.BytesIO()
            with wave.open(buf, 'wb') as wav:
                tts.synthesize_wav(request['text'], wav)
            if buf.tell() > 8_000_000:
                raise ValueError('Audio output limit')
            result = {'audio': base64.b64encode(buf.getvalue()).decode('ascii')}
        else:
            raise ValueError('Operation')
        result['worker_ms'] = round((time.perf_counter() - started) * 1000)
        sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8') + b'\n')
        sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
