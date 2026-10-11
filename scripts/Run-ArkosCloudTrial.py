"""Cloud trial against a FAKE provider: browser -> task center -> HTTP gateway -> official SDK
-> local fake Messages API. No real keys, no paid calls, loopback only.

  python -m pip install -r requirements-cloud.txt
  python scripts/Run-ArkosCloudTrial.py --state-dir <carpeta-de-prueba> [--no-browser] [--control]

--control adds a loopback control endpoint used by the browser test (scripted provider
faults, budget exhaustion, stopping the gateway). It never exists outside this trial.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import webbrowser

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from arkos_hermes.bridge import HermesBridge
from arkos_cloud.config import ClientConfig, GatewayConfig
from arkos_cloud.gateway import CloudGateway, utc_day
from arkos_cloud.server import GatewayServer
from arkos_pilot.cloud_link import CloudLink
from arkos_pilot.task_center import TaskCenter
from tests.fake_anthropic import FakeAnthropic

FAKE_KEY = "fake-key-for-local-tests-only"


class Trial:
    def __init__(self, state):
        try:
            from arkos_cloud.provider_anthropic import AnthropicProvider
            import anthropic  # noqa: F401
        except ImportError:
            sys.exit("Instalá requirements-cloud.txt: la prueba usa el SDK oficial contra una API falsa local.")
        self.state = Path(state)
        self.fake = FakeAnthropic()
        config = GatewayConfig.from_mapping(json.loads((REPO / "config" / "cloud-gateway.example.json").read_text(encoding="utf-8")))
        provider = AnthropicProvider(config.disclosure.model, FAKE_KEY, base_url=self.fake.url)
        self.gateway = CloudGateway(config, self.state / "gateway" / "ledger.sqlite3", provider)
        token = self.gateway.ledger.issue_token("pilot")
        self.gateway_server = None
        self.start_gateway(0)
        client = json.loads((REPO / "config" / "cloud-client.example.json").read_text(encoding="utf-8"))
        client["gateway_url"] = self.gateway_server.url
        cloud = CloudLink(self.state / "pc", ClientConfig.from_mapping(client), token)
        local = HermesBridge(sys.executable, REPO, self.state / "pc" / "synthetic-home",
                             runner=REPO / "tests" / "fixtures" / "chat_runner.py")
        self.center = TaskCenter(self.state / "pc", bridge=local, chat_mode="synthetic", cloud=cloud)

    def start_gateway(self, port):
        self.gateway_server = GatewayServer(self.gateway, port=port, access_log=None)
        self.port = self.gateway_server.server_address[1]
        threading.Thread(target=self.gateway_server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def stop_gateway(self):
        if self.gateway_server:
            self.gateway_server.shutdown()
            self.gateway_server.server_close()
            self.gateway_server = None

    def control(self, path, body):
        if path == "/script":
            self.fake.script.append(body["action"] if isinstance(body["action"], str) else tuple(body["action"]))
            if body.get("release"):
                self.fake.release.clear()
            return {"ok": True}
        if path == "/release":
            self.fake.release.set()
            return {"ok": True}
        if path == "/requests":
            return {"count": len(self.fake.requests),
                    "messages": [len(r["body"].get("messages", [])) for r in self.fake.requests],
                    "contents": [[m["content"] for m in r["body"].get("messages", [])] for r in self.fake.requests],
                    "keys": sorted({k for r in self.fake.requests for k in r["body"]})}
        if path == "/exhaust":
            limit = self.gateway.config.global_monthly_micro_usd
            self.gateway.ledger.reserve("operator", "trial-exhaust", "d", limit, utc_day(), 10**12, 10**12)
            return {"ok": True}
        if path == "/restore-budget":
            self.gateway.ledger.request_cancel("operator", "trial-exhaust")
            return {"ok": True}
        if path == "/gateway/stop":
            self.stop_gateway()
            return {"ok": True}
        if path == "/gateway/start":
            if not self.gateway_server:
                self.start_gateway(self.port)
            return {"ok": True}
        if path == "/ledger":
            rows = self.gateway.ledger.db.execute("SELECT request_id, state, charged, cancel_requested FROM calls "
                                                  "WHERE user_id='pilot'").fetchall()
            return {"calls": [dict(request_id=r[0], state=r[1], charged=r[2], cancel_requested=r[3]) for r in rows]}
        raise KeyError(path)

    def serve_control(self):
        trial = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0")) or 0) or b"{}")
                try:
                    data, status = trial.control(self.path, body), 200
                except Exception as exc:  # trial tool: report and keep running
                    data, status = {"error": type(exc).__name__}, 400
                raw = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{server.server_address[1]}"

    def close(self):
        self.center.server_close()
        self.stop_gateway()
        self.gateway.close()
        self.fake.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--control", action="store_true")
    args = parser.parse_args()
    trial = Trial(args.state_dir)
    url = trial.center.origin + "/#key=" + trial.center.key
    print("PRUEBA CLOUD con proveedor FALSO local: sin claves reales ni llamadas pagas. Cerrar con Ctrl+C.", flush=True)
    print(json.dumps({"url": url, "control": trial.serve_control() if args.control else None}), flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        trial.center.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        trial.close()


if __name__ == "__main__":
    main()
