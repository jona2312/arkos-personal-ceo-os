"""One explicitly authorized ElevenLabs sample through Hermes' real TTS tool.

Requires the temporary profile configuration made by Configure-HermesElevenLabsTrial.
The key is read from that private profile, never printed. This command does not
change the profile; restore it separately after the test. Run in the Hermes
environment with tts-premium installed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hermes-source', type=Path, required=True)
    parser.add_argument('--profile-home', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--voice-id', required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--allow-credit-use', action='store_true')
    args = parser.parse_args()
    if not args.allow_credit_use:
        raise SystemExit('This test requires explicit authorization for one credit-consuming sample.')
    if not re.fullmatch(r'[A-Za-z0-9]{15,40}', args.voice_id):
        raise SystemExit('Invalid voice ID format.')
    profile = args.profile_home.resolve(strict=True)
    workspace = args.workspace.resolve(strict=True)
    if profile.name != 'arkos-pilot':
        raise SystemExit('Expected arkos-pilot.')
    import yaml
    cfg = yaml.safe_load((profile / 'config.yaml').read_text(encoding='utf-8'))
    tts = cfg.get('tts', {})
    if tts.get('provider') != 'elevenlabs' or tts.get('elevenlabs', {}).get('voice_id') != args.voice_id:
        raise SystemExit('Configure the temporary ElevenLabs provider and requested voice ID first.')
    config_hash = hashlib.sha256((profile / 'config.yaml').read_bytes()).hexdigest()
    os.environ['HERMES_HOME'] = str(profile)
    os.environ['HERMES_WRITE_SAFE_ROOT'] = str(workspace)
    sys.path.insert(0, str(args.hermes_source.resolve(strict=True)))
    from dotenv import dotenv_values
    key = dotenv_values(profile / '.env').get('ELEVENLABS_API_KEY') or ''
    if not key:
        raise SystemExit('No key supplied.')
    os.environ['ELEVENLABS_API_KEY'] = key
    logging.disable(logging.CRITICAL)  # no SDK failure bodies/headers in console logs
    report = {'kind': 'single authorized Hermes TTS tool call; not Desktop auto-reply',
              'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'voice_id': args.voice_id, 'model_id': tts['elevenlabs'].get('model_id'),
              'key_source': 'private profile .env', 'default_provider': 'elevenlabs',
              'generation_calls_requested': 1,
              'text': 'Jonathan, ¿estás por ahí?',
              'speaker_audibility': 'pending'}

    def get_json(route):
        # Only ElevenLabs official HTTPS origin; never follow credential redirects.
        class NoRedirects(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise ValueError('Redirect refused')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirects())
        req = urllib.request.Request('https://api.elevenlabs.io' + route, headers={'xi-api-key': key})
        try:
            with opener.open(req, timeout=25) as resp:
                return json.load(resp), 200
        except urllib.error.HTTPError as exc:
            return None, exc.code

    before = None
    try:
        voice, status = get_json('/v1/voices/' + args.voice_id)
        report['voice_metadata_http_status'] = status
        if voice:
            report['voice_name'] = voice.get('name')
            report['voice_category'] = voice.get('category')
        before, sub_status = get_json('/v1/user/subscription')
        report['usage_read_http_status'] = sub_status
        from tools.tts_tool import text_to_speech_tool
        output = workspace / ('elevenlabs-trial-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.mp3')
        start = time.perf_counter()
        # Hermes uses configured tts.provider as authoritative. A per-call
        # provider argument cannot switch an Edge profile to ElevenLabs.
        result = json.loads(text_to_speech_tool(report['text'], str(output)))
        report['actual_provider'] = result.get('provider')
        report['generation_s'] = round(time.perf_counter() - start, 3)
        if result.get('success') and result.get('provider') == 'elevenlabs' and output.is_file():
            report.update(status='audio_generated', audio=str(output), bytes=output.stat().st_size,
                          sha256=hashlib.sha256(output.read_bytes()).hexdigest())
        else:
            error = str(result.get('error') or 'provider_mismatch_or_missing_audio').replace(key, '[REDACTED]')
            # Keep useful service failure text, bounded and credential-redacted.
            error = re.sub(r'sk_[A-Za-z0-9_-]+', '[REDACTED]', error)
            report.update(status='failed', error=error[:700])
        if before:
            after, after_status = get_json('/v1/user/subscription')
            report['usage_after_http_status'] = after_status
            if after and isinstance(before.get('character_count'), int) and isinstance(after.get('character_count'), int):
                report['account_character_count_delta'] = after['character_count'] - before['character_count']
                report['usage_caveat'] = 'Account-wide count; may include concurrent usage. Not a currency charge.'
    except Exception as exc:
        report.update(status='failed', error_type=type(exc).__name__)
    finally:
        os.environ.pop('ELEVENLABS_API_KEY', None)
        key = ''
        report['profile_config_unchanged_during_test'] = config_hash == hashlib.sha256((profile / 'config.yaml').read_bytes()).hexdigest()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report.get('status') == 'audio_generated' else 1


if __name__ == '__main__':
    raise SystemExit(main())
