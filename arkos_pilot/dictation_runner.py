"""Private worker: fixed offline CPU inference, WAV stdin / JSON stdout."""
import io
import json
import os
import sys
import wave


def main():
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    # Fail closed on Python network calls, including accidental library downloads.
    def offline(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo', 'socket.bind'):
            raise RuntimeError('Dictation is offline')
    sys.addaudithook(offline)
    import numpy as np
    from faster_whisper import WhisperModel
    raw = sys.stdin.buffer.read(960045)
    if len(raw) > 960044:
        raise ValueError('Audio limit')
    with wave.open(io.BytesIO(raw), 'rb') as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
            raise ValueError('Audio format')
        count = source.getnframes()
        if not 1600 <= count <= 480000:
            raise ValueError('Audio duration')
        frames = source.readframes(count)
        if len(frames) != count * 2:
            raise ValueError('Truncated audio')
    audio = np.frombuffer(frames, dtype='<i2').astype(np.float32) / 32768
    model = WhisperModel(sys.argv[1], device='cpu', compute_type='int8',
                         cpu_threads=4, local_files_only=True)
    segments, _ = model.transcribe(audio, language='es', beam_size=1, vad_filter=False,
                                  condition_on_previous_text=False)
    text = ' '.join(segment.text.strip() for segment in segments).strip()
    if len(text) > 4000:
        raise ValueError('Text limit')
    sys.stdout.buffer.write(json.dumps({'text': text}, ensure_ascii=False).encode('utf-8'))


if __name__ == '__main__':
    main()
