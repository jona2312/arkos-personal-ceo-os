"""Apply the versioned pilot personality, preserving the previous SOUL in a backup.

Requires an explicit profile path and refuses profiles other than arkos-pilot.
Does not read .env, change credentials, tool permissions, or other profiles.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile-home', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--apply', action='store_true', help='Without this flag, preview only.')
    args = parser.parse_args()
    profile = args.profile_home.resolve(strict=True)
    workspace = args.workspace.resolve(strict=True)
    repo = Path(__file__).resolve().parents[1]
    if profile.name != 'arkos-pilot' or not (profile / 'config.yaml').is_file():
        raise SystemExit('Expected an existing arkos-pilot profile with config.yaml.')
    if not workspace.is_dir() or workspace == repo:
        raise SystemExit('Workspace must be a directory distinct from the repository.')
    base = (repo / 'prompts/arkos_desktop_soul.md').read_text(encoding='utf-8')
    context = (repo / 'prompts/arkos_pilot_runtime_context.md').read_text(encoding='utf-8')
    context = context.replace('{{WORKSPACE}}', workspace.as_posix()).replace('{{REPOSITORY}}', repo.as_posix())
    content = base.rstrip() + '\n\n' + context.rstrip() + '\n'
    target = profile / 'SOUL.md'
    old = target.read_bytes() if target.exists() else b''
    new = content.encode('utf-8')
    backup = None
    if args.apply and old != new:
        if old:
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            backup = profile / f'SOUL.before-arkos-context-{stamp}.md'
            with backup.open('xb') as stream:
                stream.write(old)
        target.write_bytes(new)
    print(json.dumps({'applied': args.apply, 'changed': old != new,
                      'target': str(target), 'backup': str(backup) if backup else None,
                      'sha256': hashlib.sha256(new).hexdigest(),
                      'effective_for': 'new Hermes sessions'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
