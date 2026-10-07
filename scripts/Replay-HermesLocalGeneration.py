"""Replay one stored turn against managed llama.cpp, without executing tools or TTS.

The report contains counts and hashes, never history, tool arguments, reasoning,
credentials or generated prose. A replay is not an exact original wire capture.
Run with the private Hermes Python environment while the model is otherwise idle.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import urllib.parse
import urllib.request


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ValueError('Managed local endpoint redirected; refusing credentials transfer.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hermes-source', type=Path, required=True)
    parser.add_argument('--profile-home', type=Path, required=True)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--before-message-id', type=int, required=True)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--reasoning', choices=['none', 'low', 'medium'], default='none')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    profile = args.profile_home.resolve(strict=True)
    source = args.hermes_source.resolve(strict=True)
    if profile.name != 'arkos-pilot':
        raise SystemExit('Requires arkos-pilot; other profiles are not inspected.')
    import yaml
    cfg = yaml.safe_load((profile / 'config.yaml').read_text(encoding='utf-8'))
    if cfg.get('model', {}).get('provider') != 'llamacpp':
        raise SystemExit('Requires managed local llama.cpp.')
    os.environ['HERMES_HOME'] = str(profile)
    sys.path.insert(0, str(source))
    from hermes_cli.local_runtime.endpoint import managed_root
    from model_tools import get_tool_definitions
    from tools.tool_search import assemble_tool_defs
    base, token = managed_root()
    url = urllib.parse.urlsplit(base)
    if url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port or url.username or url.password:
        raise SystemExit('Requires the verified managed IPv4 loopback endpoint.')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirects())
    database = (profile / 'state.db').as_uri() + '?mode=ro'
    with sqlite3.connect(database, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        session = connection.execute(
            'SELECT COALESCE(sp.prompt,s.system_prompt) AS prompt FROM sessions s '
            'LEFT JOIN system_prompts sp ON sp.hash=s.system_prompt_hash WHERE s.id=?',
            (args.session_id,)).fetchone()
        if not session:
            raise SystemExit('Session not found.')
        messages = [{'role': 'system', 'content': session['prompt']}]
        rows = connection.execute(
            'SELECT * FROM messages WHERE session_id=? AND id<? AND active=1 ORDER BY id',
            (args.session_id, args.before_message_id))
        for row in rows:
            if row['role'] not in ('user', 'assistant', 'tool'):
                continue
            message = {'role': row['role'], 'content': row['api_content'] or row['content'] or ''}
            for key in ('tool_calls', 'tool_call_id', 'reasoning_content'):
                if row[key]:
                    message[key] = json.loads(row[key]) if key == 'tool_calls' else row[key]
            messages.append(message)
    if len(messages) < 2:
        raise SystemExit('No conversation before the requested cutoff.')
    definitions = get_tool_definitions(enabled_toolsets=['file', 'todo', 'tts'],
        disabled_toolsets=cfg.get('agent', {}).get('disabled_toolsets'), quiet_mode=True)
    definitions = assemble_tool_defs(definitions, context_length=65536).tool_defs
    body = {'model': cfg['model']['default'], 'messages': messages, 'tools': definitions,
            'max_tokens': 1024, 'temperature': 1, 'seed': args.seed,
            'reasoning_effort': args.reasoning, 'stream': True,
            'stream_options': {'include_usage': True}}
    request = urllib.request.Request(base.rstrip('/') + '/v1/chat/completions',
        data=json.dumps(body).encode(),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    started = time.perf_counter()
    content, finish, first_text, usage = '', None, None, None
    tool_indexes = set()
    with opener.open(request, timeout=180) as response:
        for line in response:
            if not line.startswith(b'data: '):
                continue
            data = line[6:].strip()
            if data == b'[DONE]':
                break
            chunk = json.loads(data)
            if chunk.get('usage'):
                usage = {k: chunk['usage'].get(k) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
            for choice in chunk.get('choices', []):
                delta = choice.get('delta', {})
                if delta.get('content'):
                    if first_text is None:
                        first_text = round(time.perf_counter() - started, 3)
                    content += delta['content']
                tool_indexes.update(call.get('index') for call in delta.get('tool_calls', []))
                finish = choice.get('finish_reason') or finish
    report = {'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'kind': 'one reconstructed local SSE request; no tool execution or audio',
              'session_id': args.session_id, 'before_message_id': args.before_message_id,
              'history_messages': len(messages), 'seed': args.seed, 'reasoning': args.reasoning,
              'temperature': 1, 'max_tokens': 1024, 'finish_reason': finish,
              'first_text_s': first_text, 'total_s': round(time.perf_counter() - started, 3),
              'response_characters': len(content),
              'response_sha256': hashlib.sha256(content.encode()).hexdigest(),
              'tool_call_count': len(tool_indexes), 'usage': usage,
              'human_review_required': True, 'history_exported': False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if finish else 1


if __name__ == '__main__':
    raise SystemExit(main())
