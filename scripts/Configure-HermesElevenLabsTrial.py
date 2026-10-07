"""Connect/restore an explicitly requested, temporary ElevenLabs Desktop trial.

Secrets are entered without echo and stored only in the selected profile .env.
Backup data stays under that profile, never in the repository. Does not buy plans.
"""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
from pathlib import Path
import re


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile-home', type=Path, required=True)
    parser.add_argument('--voice-id')
    parser.add_argument('--restore', type=Path)
    parser.add_argument('--allow-credit-use', action='store_true')
    args = parser.parse_args()
    import yaml
    from dotenv import dotenv_values, set_key, unset_key
    profile = args.profile_home.resolve(strict=True)
    if profile.name != 'arkos-pilot':
        raise SystemExit('This command only supports arkos-pilot.')
    config_path = profile / 'config.yaml'
    env_path = profile / '.env'
    cfg = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    backup_root = profile / 'trial-backups'
    if args.restore:
        state_path = args.restore.resolve(strict=True)
        if not state_path.is_relative_to(backup_root.resolve()):
            raise SystemExit('Restore state must belong to this profile.')
        state = json.loads(state_path.read_text(encoding='utf-8'))
        current_key = dotenv_values(env_path).get('ELEVENLABS_API_KEY') or ''
        restored_key = False
        if hashlib.sha256(current_key.encode()).hexdigest() == state['trial_key_sha256']:
            old = dotenv_values(state_path.parent / 'env.before').get('ELEVENLABS_API_KEY')
            if old is None:
                unset_key(str(env_path), 'ELEVENLABS_API_KEY')
            else:
                set_key(str(env_path), 'ELEVENLABS_API_KEY', old)
            restored_key = True
        if cfg.get('tts', {}).get('provider') == 'elevenlabs':
            cfg['tts']['provider'] = state['provider_before']
        section = cfg.get('tts', {}).get('elevenlabs', {})
        before = state.get('elevenlabs_before') or {}
        for field, trial_value in state.get('trial_voice_fields', {}).items():
            if section.get(field) == trial_value:
                if field in before:
                    section[field] = before[field]
                else:
                    section.pop(field, None)
        if not section and state.get('elevenlabs_before') is None:
            cfg.get('tts', {}).pop('elevenlabs', None)
        config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding='utf-8')
        print(json.dumps({'provider': cfg['tts']['provider'], 'trial_key_restored_or_removed': restored_key}))
        return
    if not args.allow_credit_use or not re.fullmatch(r'[A-Za-z0-9]{15,40}', args.voice_id or ''):
        raise SystemExit('Explicit credit authorization and a valid voice ID are required.')
    key = getpass.getpass('ElevenLabs key (hidden; private profile only): ').strip()
    if not key:
        raise SystemExit('No key supplied.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = backup_root / ('elevenlabs-' + stamp)
    backup.mkdir(parents=True)
    (backup / 'config.before.yaml').write_bytes(config_path.read_bytes())
    (backup / 'env.before').write_bytes(env_path.read_bytes() if env_path.exists() else b'')
    trial_voice_fields = {'voice_id': args.voice_id, 'model_id': 'eleven_flash_v2_5'}
    state = {'provider_before': cfg.get('tts', {}).get('provider', 'edge'),
             'elevenlabs_before': cfg.get('tts', {}).get('elevenlabs'),
             'trial_voice_fields': trial_voice_fields,
             'trial_key_sha256': hashlib.sha256(key.encode()).hexdigest()}
    (backup / 'state.json').write_text(json.dumps(state), encoding='utf-8')
    set_key(str(env_path), 'ELEVENLABS_API_KEY', key)
    cfg.setdefault('tts', {})['provider'] = 'elevenlabs'
    cfg['tts'].setdefault('elevenlabs', {}).update(trial_voice_fields)
    config_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding='utf-8')
    key = ''
    print(json.dumps({'configured': True, 'profile': str(profile), 'provider': 'elevenlabs',
                      'voice_id': args.voice_id, 'restore_state': str(backup / 'state.json'),
                      'api_key_exported': False}))


if __name__ == '__main__':
    main()
