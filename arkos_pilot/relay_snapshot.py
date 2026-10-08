"""Bounded, read-only adapter from relay snapshot v1 to display fields.

No credentials, network, queue access, artifact opening or execution.
"""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import time

MAX_BYTES = 1048576
STATES = {'awaiting_approval', 'approved', 'claimed', 'running', 'succeeded', 'failed', 'unknown', 'rejected', 'cancelled'}
ACTIONS = {'note.create', 'document.create', 'video.clip'}
DEVICE = re.compile(r'dev_[0-9a-f]{32}')
TASK = re.compile(r'tsk_[0-9a-f]{32}')


def empty(status='not_configured'):
    return dict(projection_version=1, sync_status=status, device_status='unknown', last_sync=None, truncated=False, tasks=[])


def date(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid date')
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def text(value, limit):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError('Invalid display text')
    return value


def project(snapshot, device_id, now):
    if not isinstance(snapshot, dict) or snapshot.get('schema') != 'arkos.relay.snapshot' or type(snapshot.get('schema_version')) is not int or snapshot['schema_version'] != 1 or snapshot.get('source') != 'relay' or snapshot.get('device_id') != device_id:
        raise ValueError('Invalid snapshot')
    date(snapshot['generated_at'])
    sync = snapshot['sync']
    status = sync['status']
    if status not in {'fresh', 'stale', 'offline', 'never_synced', 'unauthorized'}:
        raise ValueError('Invalid sync state')
    last = sync['last_success_at']
    last_iso = None if last is None else date(last)
    age = sync['stale_after_seconds']
    if type(age) not in (int, float) or not math.isfinite(age) or not 0 < age <= 120:
        raise ValueError('Invalid freshness limit')
    if status == 'fresh':
        status = 'current' if last is not None and 0 <= now-last <= age else 'stale'
    rows = snapshot['tasks']
    if not isinstance(rows, list) or len(rows) > 500 or type(snapshot['task_count']) is not int or snapshot['task_count'] != len(rows) or type(snapshot['truncated']) is not bool:
        raise ValueError('Invalid task count')
    tasks, ids = [], set()
    for row in rows:
        task_id = row['remote_id']
        if not isinstance(task_id, str) or not TASK.fullmatch(task_id) or task_id in ids or row['origin'] != 'relay' or row['state'] not in STATES or row['action'] not in ACTIONS or row['for_this_device'] is not True or row['target_device_id'] not in (None, device_id):
            raise ValueError('Invalid task or destination')
        ids.add(task_id)
        summary = row['summary']
        title = text(summary['title'], 280)[:180]
        result = row['result']
        if result is not None and not isinstance(result, dict):
            raise ValueError('Invalid result')
        message = '' if result is None else text(result.get('message', ''), 500)
        tasks.append(dict(id=task_id, origin='relay', title=title, state=row['state'], updated_at=date(row['updated_at']), result_summary=message, result_availability='metadata_only' if result is not None else 'not_available'))
    # Revocation must hide the cached cards, even if a producer retained them.
    return dict(projection_version=1, sync_status=status, device_status='unknown', last_sync=last_iso, truncated=snapshot['truncated'], tasks=[] if status in {'unauthorized', 'never_synced'} else tasks)


def read_view(path=None, device_id=None, now=None):
    if path is None:
        return empty()
    try:
        path = Path(path)
        if path.is_symlink() or not path.is_file():
            raise ValueError('Invalid file')
        # Bound the actual read, not just a potentially outdated stat result.
        with path.open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Oversized file')
        return project(json.loads(data.decode('utf-8')), device_id, time.time() if now is None else now)
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        # Never expose configured paths, raw payloads or filesystem errors.
        return empty('unavailable')
