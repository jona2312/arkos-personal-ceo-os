"""Send repeatable, local daily tasks to the real Hermes CLI and verify artifacts.

Use the private Hermes Python environment. Keeps a dedicated session and a fresh
subdirectory; external-account tasks are never submitted by this script.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hermes-source', type=Path, required=True)
    parser.add_argument('--profile-home', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    profile = args.profile_home.resolve(strict=True)
    workspace = args.workspace.resolve(strict=True)
    source = args.hermes_source.resolve(strict=True)
    import yaml
    config = yaml.safe_load((profile / 'config.yaml').read_text(encoding='utf-8'))
    if profile.name != 'arkos-pilot' or config.get('model', {}).get('provider') != 'llamacpp':
        raise SystemExit('Requires the local llama.cpp arkos-pilot profile.')
    # Verify the same local-only URL boundary as the voice benchmark.
    import importlib.util
    spec = importlib.util.spec_from_file_location('voice_trial', repo / 'scripts/Test-HermesVoicePipeline.py')
    trial = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trial)
    trial.local_url(config['model']['base_url'])
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run_dir = workspace / ('rutina-' + stamp)
    run_dir.mkdir()
    queries = run_dir / '.queries'
    queries.mkdir()
    session_name = 'ARKOS rutina ' + stamp
    env = os.environ.copy()
    env.update(HERMES_HOME=str(profile), HERMES_WRITE_SAFE_ROOT=str(workspace),
               PYTHONPATH=str(source), PYTHONIOENCODING='utf-8',
               TEMP=str(workspace / '.tmp'), TMP=str(workspace / '.tmp'))
    (workspace / '.tmp').mkdir(exist_ok=True)
    catalog = json.loads((repo / 'config/hermes-daily-tasks.json').read_text(encoding='utf-8'))
    all_cases = {case['id']: case for group in ('voice_trials', 'daily_tasks') for case in catalog[group]}
    filenames = {'plan': 'plan-del-dia.md', 'shopping': 'compras.md',
                 'note': 'ideas-arkos.md', 'mail_draft': 'correo-borrador.md'}
    case_ids = ['identity', 'date_set', 'date_correct', 'date_recall',
                'plan', 'shopping', 'note', 'mail_draft', 'summary', 'voice_id']
    report = {'kind': 'real Hermes CLI; text input, not microphone input',
              'session_name': session_name, 'workspace': str(run_dir), 'cases': [],
              'external_connections_enabled': False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    failed = False
    for case_id in case_ids:
        case = all_cases[case_id]
        prompt = case['prompt']
        for filename in filenames.values():
            prompt = prompt.replace(filename, (run_dir / filename).as_posix())
        prompt += '\nPrueba autorizada por Jona. Usá solo herramientas de archivos dentro de esa carpeta cuando haga falta. No envíes mensajes ni crees eventos externos. Respondé brevemente.'
        query_file = queries / (case_id + '.txt')
        query_file.write_text(prompt, encoding='utf-8')
        command = [sys.executable, '-m', 'hermes_cli.main', 'chat', '--oneshot', '--quiet',
                   '--in', str(run_dir), '--continue', session_name, '--create-if-missing',
                   '--max-turns', '6', '--run-budget', '90', '--reasoning', 'low',
                   '--query-file', str(query_file)]
        started = time.perf_counter()
        row = {'id': case_id, 'prompt': prompt}
        try:
            result = subprocess.run(command, cwd=source, env=env, capture_output=True,
                                    text=True, encoding='utf-8', timeout=120)
            row.update(exit_code=result.returncode, response=result.stdout.strip(),
                       elapsed_to_cli_exit_s=round(time.perf_counter()-started, 3))
            if result.returncode:
                row['status'] = 'failed'
            elif case_id in filenames:
                output = run_dir / filenames[case_id]
                if output.is_file() and output.stat().st_size:
                    raw = output.read_bytes()
                    row.update(status='artifact_verified', artifact=str(output), bytes=len(raw),
                               sha256=hashlib.sha256(raw).hexdigest(), content=raw.decode('utf-8'))
                else:
                    row['status'] = 'failed_missing_artifact'
            else:
                row['status'] = 'response_received_review_required'
        except subprocess.TimeoutExpired:
            row.update(status='timeout', elapsed_to_cli_exit_s=round(time.perf_counter()-started, 3))
        report['cases'].append(row)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if row['status'] in ('failed', 'failed_missing_artifact', 'timeout'):
            failed = True
            break
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
