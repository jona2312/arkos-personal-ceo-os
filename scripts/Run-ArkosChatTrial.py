"""Deliberate synthetic UI acceptance, not a fallback for an unavailable model."""
import argparse
from pathlib import Path
import sys
import webbrowser

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arkos_hermes.bridge import HermesBridge
from arkos_pilot.task_center import TaskCenter

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--state-dir', type=Path, required=True)
parser.add_argument('--port', type=int, default=0)
parser.add_argument('--no-browser', action='store_true')
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
bridge = HermesBridge(sys.executable, repo, args.state_dir/'synthetic-home',
                      runner=repo/'tests'/'fixtures'/'chat_runner.py')
server = TaskCenter(args.state_dir, port=args.port, bridge=bridge, chat_mode='synthetic')
url = server.origin+'/#key='+server.key
print('PRUEBA SINTÉTICA; Hermes y Qwen no conectados. Cerrar con Ctrl+C.', flush=True)
print(url, flush=True)
if not args.no_browser:
    webbrowser.open(url)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
finally:
    server.server_close()
