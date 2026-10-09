"""Guided local launch: standard library only; no installation or credentials."""
import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import socket
import sys

from .relay_snapshot import DEVICE, read_view


def default_state():
    if sys.platform == 'win32' and os.environ.get('LOCALAPPDATA'):
        return Path(os.environ['LOCALAPPDATA']) / 'ArkosTaskCenterTrial'
    # Non-Windows trials must deliberately choose a directory.
    return None


def preflight(state_dir, port=0, relay_snapshot=None, relay_device_id=None):
    checks, warnings = [], []
    def check(name, ok, message):
        checks.append(dict(name=name, ok=bool(ok), message=message))
    check('python', sys.version_info >= (3, 11), 'Se requiere Python 3.11 o superior.')
    try:
        importlib.import_module('sqlite3')
        sqlite_ok = True
    except ImportError:
        sqlite_ok = False
    check('sqlite', sqlite_ok, 'SQLite de Python debe estar disponible para la cola local.')
    check('web', all((Path(__file__).with_name('web') / name).is_file() for name in ('index.html', 'app.js', 'chat.js', 'neural.js', 'remote-view.js', 'style.css', 'mark.svg')), 'El checkout debe incluir todos los archivos de la pantalla.')
    path = Path(state_dir) if state_dir is not None else None
    safe = path is not None
    try:
        if path is not None:
            safe = not path.is_symlink() and (not path.exists() or path.is_dir())
            for name in ('outputs', 'queue.sqlite3'):
                child = path / name
                safe = safe and not child.is_symlink()
                if child.exists():
                    safe = safe and (child.is_dir() if name == 'outputs' else child.is_file())
            parent = path
            while not parent.exists() and parent != parent.parent:
                parent = parent.parent
            safe = safe and parent.is_dir() and os.access(parent, os.W_OK)
    except OSError:
        safe = False
    check('state', safe, 'Elegí una carpeta de prueba escribible; no usar archivos, enlaces ni la instalación existente.')
    port_ok = type(port) is int and 0 <= port <= 65535
    if port_ok:
        try:
            with socket.socket() as listener:
                listener.bind(('127.0.0.1', port))
        except OSError:
            port_ok = False
    check('port', port_ok, 'El puerto local debe estar libre. Usá --port 0 para elegir uno automáticamente.')
    relay_ok = (relay_snapshot is None) == (relay_device_id is None)
    if relay_device_id is not None:
        relay_ok = relay_ok and isinstance(relay_device_id, str) and bool(DEVICE.fullmatch(relay_device_id))
    check('relay_config', relay_ok, 'Snapshot e ID de dispositivo se configuran juntos; la pantalla no vincula dispositivos.')
    if relay_ok and relay_snapshot is not None:
        view = read_view(relay_snapshot, relay_device_id)
        if view['sync_status'] != 'current':
            warnings.append('La copia del relay no está actualizada o no está disponible; la pantalla local puede abrirse igual.')
    ffmpeg = bool(shutil.which('ffmpeg'))
    if not ffmpeg:
        warnings.append('FFmpeg no está en PATH: notas disponibles, recortes pendientes. No se descarga ni instala automáticamente.')
    return dict(ready=all(c['ok'] for c in checks), checks=checks, warnings=warnings,
                capabilities=dict(notes=sqlite_ok, clips=ffmpeg, hermes_chat=False, voice=False),
                python_version='.'.join(map(str, sys.version_info[:3])))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Apertura guiada del centro de tareas ARKOS')
    parser.add_argument('--state-dir', type=Path, default=default_state())
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--relay-snapshot', type=Path)
    parser.add_argument('--relay-device-id')
    parser.add_argument('--check-only', action='store_true', help='Solo diagnóstico: no crea carpetas ni abre la pantalla')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    report = preflight(args.state_dir, args.port, args.relay_snapshot, args.relay_device_id)
    if args.check_only:
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return 0 if report['ready'] else 2
    for row in report['checks']:
        if not row['ok']:
            print('Pendiente: ' + row['message'], file=sys.stderr)
    for warning in report['warnings']:
        print('Aviso: ' + warning, file=sys.stderr)
    if not report['ready']:
        return 2
    # Only the deliberate launch enters the existing server, which creates state.
    from .task_center import main as center_main
    options = ['--state-dir', str(args.state_dir), '--port', str(args.port)]
    if args.no_browser:
        options.append('--no-browser')
    if args.relay_snapshot is not None:
        options.extend(['--relay-snapshot', str(args.relay_snapshot), '--relay-device-id', args.relay_device_id])
    try:
        center_main(options)
    except (OSError, importlib.import_module('sqlite3').Error):
        print('No se pudo abrir la pantalla. Revisá permisos, estado de SQLite y puerto; no se ejecutó ninguna tarea. Probá --check-only.', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
