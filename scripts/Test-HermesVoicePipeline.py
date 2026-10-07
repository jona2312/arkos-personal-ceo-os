"""Five synthetic voice-pipeline trials against an already running local Hermes.

Uses Desktop's real STT/TTS HTTP routes and the configured local llama.cpp model.
Measures upload -> complete audio returned, not speech-end -> first audible sound.
Does not record the microphone, play audio, execute model tools, or use paid APIs.
Run with the Python environment that belongs to this Hermes installation.
"""
import argparse
import base64
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def local_url(value):
    parsed = urllib.parse.urlsplit(value)
    try:
        loopback = ipaddress.ip_address(parsed.hostname or '').is_loopback
    except ValueError:
        loopback = False
    if parsed.scheme != 'http' or not loopback or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Only an explicit credential-free HTTP loopback model URL is allowed.')
    return value.rstrip('/')


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect refused for local benchmark endpoint.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hermes-source', type=Path, required=True)
    parser.add_argument('--profile-home', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    source = args.hermes_source.resolve(strict=True)
    profile = args.profile_home.resolve(strict=True)
    workspace = args.workspace.resolve(strict=True)
    repo = Path(__file__).resolve().parents[1]
    if profile.name != 'arkos-pilot':
        raise SystemExit('This trial is scoped to arkos-pilot.')
    import yaml
    config = yaml.safe_load((profile / 'config.yaml').read_text(encoding='utf-8'))
    model = config.get('model', {})
    base_url = local_url(model.get('base_url', ''))
    if model.get('provider') != 'llamacpp':
        raise SystemExit('Local llama.cpp provider required; no paid fallback.')
    if config.get('stt', {}).get('provider') != 'local':
        raise SystemExit('Local STT required; refusing to upload fixture audio elsewhere.')
    if config.get('tts', {}).get('provider') not in ('edge', 'piper'):
        raise SystemExit('Only the approved Edge/Piper providers are allowed.')
    fixture_dir = workspace / 'voice-benchmark' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    fixture_dir.mkdir(parents=True)
    os.environ['HERMES_HOME'] = str(profile)
    os.environ['HERMES_WRITE_SAFE_ROOT'] = str(workspace)
    sys.path.insert(0, str(source))
    from gateway import host_rendezvous as hr
    from hermes_cli.local_runtime.endpoint import managed_root
    from tools.tts_tool_local import _generate_piper_tts
    managed = managed_root()
    if not managed or local_url(managed[0]) + '/v1' != base_url:
        raise SystemExit('The configured URL is not the verified managed local model endpoint.')
    model_token = managed[1]  # internal loopback authentication; never exported
    record = hr.read_record(hr.ROLE_DESKTOP_SERVE)
    if not record:
        raise SystemExit('Start Hermes Desktop for arkos-pilot first.')
    token = hr.read_token(hr.ROLE_DESKTOP_SERVE)
    desktop_url = f'http://127.0.0.1:{record.port}'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirects())

    def post(url, payload, desktop=False):
        headers = {'Content-Type': 'application/json'}
        if desktop:
            headers['X-Hermes-Session-Token'] = token
        else:
            headers['Authorization'] = 'Bearer ' + model_token
        request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers)
        with opener.open(request, timeout=180) as response:
            return json.load(response)

    # Preparing input audio is not part of the measured response latency.
    cases = json.loads((repo / 'config/hermes-daily-tasks.json').read_text(encoding='utf-8'))['voice_trials']
    fixtures = []
    for case in cases:
        path = fixture_dir / (case['id'] + '-input.wav')
        _generate_piper_tts(case['prompt'], str(path), {'provider': 'piper', 'piper': {
            'voice': 'es_AR-daniela-high', 'voices_dir': str(profile / 'cache/piper-voices')}})
        fixtures.append((case, path))
    report = {
        'kind': 'synthetic sequential pipeline; not a human microphone or speaker test',
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'metric': 'input WAV upload start to complete response audio received',
        'excluded': ['microphone capture', 'end-of-speech detection', 'native chat orchestration',
                     'tool calls', 'first streamed audio', 'physical speaker playback'],
        'desktop_stt_tts_routes': True,
        'model': model['default'], 'model_thinking': False,
        'tts': {'provider': config['tts']['provider'],
                'edge_voice': config['tts'].get('edge', {}).get('voice'),
                'edge_speed': config['tts'].get('edge', {}).get('speed'),
                'piper_voice': config['tts'].get('piper', {}).get('voice')},
        'cases': [],
        'human_speech_end_to_first_audible_median_s': None,
    }
    soul = (profile / 'SOUL.md').read_text(encoding='utf-8')
    messages = [{'role': 'system', 'content': soul + '\nPrueba sintética: responde en una frase breve, sin herramientas.'}]
    args.report.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    for case, path in fixtures:
        row = {'id': case['id'], 'input_text': case['prompt'], 'input_wav': str(path)}
        started = time.perf_counter()
        stage = 'stt'
        try:
            data_url = 'data:audio/wav;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')
            started = time.perf_counter()
            transcript = post(desktop_url + '/api/audio/transcribe', {'data_url': data_url, 'mime_type': 'audio/wav'}, True)
            after_stt = time.perf_counter()
            if not transcript.get('ok') or not transcript.get('transcript'):
                raise RuntimeError('Empty or failed transcription')
            row['transcript'] = transcript['transcript']
            row['stt_s'] = round(after_stt - started, 3)
            messages.append({'role': 'user', 'content': row['transcript']})
            stage = 'llm'
            response = post(base_url + '/chat/completions', {
                'model': model['default'], 'messages': messages, 'temperature': 0.1,
                'max_tokens': 256, 'chat_template_kwargs': {'enable_thinking': False}})
            after_llm = time.perf_counter()
            answer = response['choices'][0]['message']['content']
            if not answer or response['choices'][0].get('finish_reason') == 'length':
                raise RuntimeError('Empty or truncated model answer')
            row['answer'] = answer
            row['llm_s'] = round(after_llm - after_stt, 3)
            messages.append({'role': 'assistant', 'content': answer})
            stage = 'tts'
            audio = post(desktop_url + '/api/audio/speak', {'text': answer}, True)
            completed = time.perf_counter()
            header, encoded = audio.get('data_url', '').split(',', 1)
            raw = base64.b64decode(encoded, validate=True)
            if not audio.get('ok') or not header.startswith('data:audio/') or not raw:
                raise RuntimeError('Invalid TTS response')
            row['tts_s'] = round(completed - after_llm, 3)
            row['pipeline_to_complete_audio_s'] = round(completed - started, 3)
            row['audio_bytes'] = len(raw)
            row['provider'] = audio.get('provider')
            suffix = '.wav' if 'wav' in header else '.mp3'
            output = fixture_dir / (case['id'] + '-reply' + suffix)
            output.write_bytes(raw)
            row['output_audio'] = str(output)
            row['status'] = 'completed'
        except Exception as exc:
            # Never include request headers, tokens, response bodies or env in errors.
            row.update(status='failed', failed_stage=stage, error_type=type(exc).__name__,
                       elapsed_s=round(time.perf_counter() - started, 3))
            if isinstance(exc, urllib.error.HTTPError):
                row['http_status'] = exc.code
        report['cases'].append(row)
        save()
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if row['status'] == 'failed':
            break  # dependent date turns must not silently continue after failure
    complete = [row for row in report['cases'] if row['status'] == 'completed']
    report['completed_count'] = len(complete)
    report['expected_count'] = len(cases)
    report['medians_s'] = ({field: round(statistics.median(row[field] for row in complete), 3)
                            for field in ('stt_s', 'llm_s', 'tts_s', 'pipeline_to_complete_audio_s')}
                           if len(complete) == len(cases) else None)
    save()
    print(json.dumps({'report': str(args.report), 'completed': len(complete), 'medians_s': report['medians_s']}), flush=True)
    return 0 if len(complete) == len(cases) else 1


if __name__ == '__main__':
    raise SystemExit(main())
