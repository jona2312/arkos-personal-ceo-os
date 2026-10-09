"""Loopback-only task center. No cloud, remote shell or Hermes credentials."""
import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import threading
from urllib.parse import urlsplit
import webbrowser

from .relay_snapshot import DEVICE, read_view
from .catalog import propose
from .core import Queue, clip_payload
from .chat import Conversations, ChatError, REQUEST_ID

WEB = Path(__file__).with_name('web')
TASK_ID = re.compile(r'^[0-9a-f]{32}$')
MAX_BODY = 650_000


@contextmanager
def queue_at(root):
    queue = Queue(root)
    try:
        yield queue
    finally:
        queue.close()


class TaskCenter(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, state_dir, port=0, relay_snapshot=None, relay_device_id=None, bridge=None, chat_mode='hermes'):
        if (relay_snapshot is None) != (relay_device_id is None) or (relay_device_id is not None and not DEVICE.fullmatch(relay_device_id)):
            raise ValueError("Configurá juntos el snapshot y el ID de dispositivo válido.")
        self.relay_snapshot = relay_snapshot
        self.relay_device_id = relay_device_id
        self.root = Path(state_dir).resolve()
        with queue_at(self.root):
            pass
        self.key = secrets.token_urlsafe(32)
        self.worker_lock = threading.Lock()
        super().__init__(('127.0.0.1', port), Handler)
        self.origin = f'http://127.0.0.1:{self.server_port}'
        self.chat = Conversations(self.root, bridge, chat_mode)

    def server_close(self):
        if hasattr(self, 'chat'):
            self.chat.close()
        super().server_close()

    def launch(self, task_id):
        if not self.worker_lock.acquire(blocking=False):
            raise ValueError('Ya hay una tarea ejecutándose. Esperá su resultado.')
        try:
            with queue_at(self.root) as queue:
                if queue.get(task_id)['state'] != 'queued':
                    raise ValueError('La tarea debe estar aprobada y en cola.')
            def work():
                try:
                    with queue_at(self.root) as queue:
                        queue.run_next(task_id=task_id)
                finally:
                    self.worker_lock.release()
            threading.Thread(target=work, daemon=True).start()
        except Exception:
            self.worker_lock.release()
            raise


class Handler(BaseHTTPRequestHandler):
    server_version = 'ArkosLocal/1'

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format, *args):
        # Do not log user payloads, paths, tokens or result URLs.
        pass

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        super().end_headers()

    def json(self, status, value):
        data = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def allowed(self, private=False, mutation=False):
        # Exact Host blocks DNS rebinding; token prevents other loopback origins
        # and cross-site requests from inspecting data or executing actions.
        if self.headers.get('Host') != urlsplit(self.server.origin).netloc:
            self.json(403, {'error': 'Host no autorizado.'})
            return False
        origin = self.headers.get('Origin')
        if origin and origin != self.server.origin:
            self.json(403, {'error': 'Origen no autorizado.'})
            return False
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.json(403, {'error': 'Solicitud externa bloqueada.'})
            return False
        if private and not secrets.compare_digest(self.headers.get('X-Arkos-Key', ''), self.server.key):
            self.json(401, {'error': 'Abrí el enlace de esta sesión desde el launcher de ARKOS.'})
            return False
        if mutation and origin != self.server.origin:
            self.json(403, {'error': 'Se requiere el origen local de ARKOS.'})
            return False
        return True

    def do_GET(self):
        path = urlsplit(self.path).path
        if not self.allowed(private=path.startswith('/api/')):
            return
        static = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/neural.js': ('neural.js', 'text/javascript; charset=utf-8'), '/remote-view.js': ('remote-view.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8'), '/mark.svg': ('mark.svg', 'image/svg+xml')}
        try:
            if path == '/api/chat':
                self.json(200, self.server.chat.status())
                return
            if path.startswith('/api/chat/'):
                rid = path.removeprefix('/api/chat/')
                if not REQUEST_ID.fullmatch(rid):
                    raise ValueError('Turno inválido.')
                self.json(200, self.server.chat.get(rid))
                return
            if path == '/chat.js':
                static[path] = ('chat.js', 'text/javascript; charset=utf-8')
            if path in static:
                name, mime = static[path]
                data = (WEB / name).read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if path == '/api/status':
                self.json(200, {'mode': 'local', 'worker_busy': self.server.worker_lock.locked(), 'ffmpeg': bool(shutil.which('ffmpeg')), 'capabilities': {'notes': True, 'clips': bool(shutil.which('ffmpeg')), 'hermes_chat': self.server.chat.bridge is not None, 'remote_sync': False, 'email': False, 'calendar': False, 'whatsapp': False}})
            elif path == '/api/remote-view':
                self.json(200, read_view(self.server.relay_snapshot, self.server.relay_device_id))
            elif path == '/api/tasks':
                with queue_at(self.server.root) as queue:
                    tasks = queue.list()
                self.json(200, {'tasks': tasks})
            elif path.startswith('/api/tasks/') and path.endswith('/artifact'):
                task_id = path.split('/')[3]
                if not TASK_ID.fullmatch(task_id):
                    raise ValueError('Identificador inválido.')
                with queue_at(self.server.root) as queue:
                    task = queue.get(task_id)
                if task['state'] != 'completed':
                    raise ValueError('Todavía no hay un resultado terminado.')
                suffix = '.md' if task['payload']['action'] == 'note' else '.mp4'
                output = self.server.root / 'outputs'
                target = output / (task_id + suffix)
                if (output.is_symlink() or output.resolve().parent != self.server.root
                        or target.is_symlink() or not target.is_file()
                        or str(target.resolve()) != str(Path(task['result']).resolve())):
                    raise ValueError('El resultado ya no está disponible en la carpeta de salidas.')
                # Stream artifacts: a video must not be loaded fully into RAM.
                with target.open('rb') as stream:
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/plain; charset=utf-8' if suffix == '.md' else 'video/mp4')
                    self.send_header('Content-Disposition', f'attachment; filename="arkos-{task_id[:8]}{suffix}"')
                    self.send_header('Content-Length', str(target.stat().st_size))
                    self.end_headers()
                    shutil.copyfileobj(stream, self.wfile)
            else:
                self.json(404, {'error': 'Recurso no encontrado.'})
        except ChatError as exc:
            self.json(exc.status, {'error': str(exc)})
        except (ValueError, OSError, sqlite3.Error):
            self.json(400, {'error': 'No se pudo consultar el recurso. Revisá el estado de la tarea y su archivo.'})

    def do_POST(self):
        if not self.allowed(private=True, mutation=True):
            return
        try:
            if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
                raise ValueError('Se requiere JSON.')
            length = int(self.headers.get('Content-Length', '0'))
            path = urlsplit(self.path).path
            limit = 200_000 if path.startswith('/api/chat') else MAX_BODY
            if self.headers.get('Transfer-Encoding') or not 0 < length <= limit:
                raise ValueError('Pedido vacío o demasiado grande.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Pedido inválido.')
            path = urlsplit(self.path).path
            if path == '/api/chat':
                self.json(202, self.server.chat.start(data))
                return
            if path.startswith('/api/chat/'):
                parts = path.strip('/').split('/')
                if len(parts) != 4 or not REQUEST_ID.fullmatch(parts[2]):
                    raise ValueError('Ruta de conversación inválida.')
                rid, action = parts[2:]
                if action == 'cancel' and not data:
                    self.json(200, self.server.chat.cancel(rid))
                elif action == 'note' and set(data) == {'proposal_id'} and isinstance(data['proposal_id'], str):
                    self.json(200, {'task': self.server.chat.create_note(rid, data['proposal_id'])})
                else:
                    raise ValueError('Acción de conversación inválida.')
                return
            if path == '/api/propose':
                goal = data.get('goal')
                if not isinstance(goal, str) or not goal.strip() or len(goal) > 4000:
                    raise ValueError('Escribí un objetivo de hasta 4000 caracteres.')
                self.json(200, propose(goal))
                return
            with queue_at(self.server.root) as queue:
                if path == '/api/tasks':
                    if data.get('action') == 'note':
                        if set(data) != {'action', 'text'}:
                            raise ValueError('Campos de nota inválidos.')
                        result = queue.add(data)
                    elif data.get('action') == 'clip':
                        if set(data) != {'action', 'source', 'start', 'duration'}:
                            raise ValueError('Campos de recorte inválidos.')
                        if not isinstance(data['source'], str) or not Path(data['source']).is_absolute():
                            raise ValueError('Indicá la ruta absoluta de un archivo de esta PC.')
                        result = queue.add(clip_payload(data['source'], data['start'], data['duration']))
                    else:
                        raise ValueError('Acción no disponible.')
                    self.json(201, {'task': result})
                    return
                parts = path.strip('/').split('/')
                if len(parts) != 4 or parts[:2] != ['api', 'tasks'] or not TASK_ID.fullmatch(parts[2]):
                    self.json(404, {'error': 'Acción no encontrada.'})
                    return
                task_id, action = parts[2:]
                if action == 'approve':
                    fingerprint = data.get('fingerprint')
                    if not isinstance(fingerprint, str):
                        raise ValueError('Revisá la tarea antes de aprobar.')
                    result = queue.approve(task_id, fingerprint)
                elif action == 'cancel':
                    result = queue.cancel(task_id)
                elif action == 'run':
                    self.server.launch(task_id)
                    self.json(202, {'accepted': True, 'task_id': task_id})
                    return
                else:
                    raise ValueError('Acción no disponible.')
                self.json(200, {'task': result})
        except ChatError as exc:
            self.json(exc.status, {'error': str(exc)})
        except ValueError as exc:
            message = str(exc) if not isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError)) else 'JSON inválido.'
            self.json(400, {'error': message})
        except (TypeError, KeyError, OverflowError):
            self.json(400, {'error': 'No se aplicó el pedido. Revisá los campos, el estado y la aprobación vigente.'})
        except (OSError, sqlite3.Error):
            self.json(409, {'error': 'No se pudo completar la operación local. Revisá el archivo o actualizá las tareas antes de volver a intentar.'})


def main(argv=None):
    parser = argparse.ArgumentParser(description='Centro de tareas ARKOS, solo en esta PC')
    parser.add_argument('--state-dir', type=Path, required=True, help='Carpeta de estado explícita; usar una carpeta de prueba al comenzar')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--relay-snapshot', type=Path, help='Snapshot de lectura explícito; no se busca automáticamente')
    parser.add_argument('--relay-device-id', help='Dispositivo esperado en el snapshot')
    parser.add_argument('--hermes-python', type=Path)
    parser.add_argument('--hermes-source', type=Path)
    parser.add_argument('--hermes-home', type=Path, help='Perfil dedicado ya autorizado y existente')
    parser.add_argument('--hermes-model', default='')
    args = parser.parse_args(argv)
    try:
        bridge = None
        settings = (args.hermes_python, args.hermes_source, args.hermes_home)
        if any(settings):
            if not all(settings) or not args.hermes_python.is_file() or not args.hermes_source.is_dir() or not args.hermes_home.is_dir():
                raise ValueError('Hermes requiere Python, fuente y perfil dedicado existentes.')
            from arkos_hermes.bridge import HermesBridge
            bridge = HermesBridge(*settings, model=args.hermes_model)
        elif args.hermes_model:
            raise ValueError('Configurá Hermes antes de elegir su modelo.')
        server = TaskCenter(args.state_dir, args.port, args.relay_snapshot, args.relay_device_id, bridge=bridge)
    except ValueError as exc:
        parser.error(str(exc))
    url = f'{server.origin}/#key={server.key}'
    print('ARKOS local. Enlace privado de esta sesión (no compartir):', flush=True)
    print(url, flush=True)
    print('Cerrar con Ctrl+C. Una tarea running interrumpida requiere revisión manual.', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
