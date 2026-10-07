"""CLI: relay server, admin bootstrap and Windows agent."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

from .contract import ContractError


def default_agent_dir():
    base = os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))
    return Path(base) / "ArkosRelayAgent"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="arkos_relay", description="ARKOS: cola persistente celular → PC")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Servidor de recepción y sincronización")
    serve.add_argument("--db", type=Path, required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)

    admin = sub.add_parser("admin", help="Alta de usuarios y canales (operador)")
    admin.add_argument("--db", type=Path, required=True)
    admin_sub = admin.add_subparsers(dest="admin_command", required=True)
    p = admin_sub.add_parser("create-user"); p.add_argument("--name", required=True)
    p = admin_sub.add_parser("issue-token"); p.add_argument("--user", required=True); p.add_argument("--label", default="phone")
    p = admin_sub.add_parser("bind-whatsapp"); p.add_argument("--user", required=True); p.add_argument("--phone", required=True)

    agent = sub.add_parser("agent", help="Agente de la PC (solo conexiones salientes)")
    agent.add_argument("--state-dir", type=Path, default=default_agent_dir())
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    p = agent_sub.add_parser("pair"); p.add_argument("--server", required=True); p.add_argument("--code", required=True)
    p.add_argument("--allow-insecure-localhost", action="store_true")
    p = agent_sub.add_parser("allow-root", help="Autorizar una carpeta local para recortes")
    p.add_argument("name"); p.add_argument("path", type=Path)
    p = agent_sub.add_parser("run"); p.add_argument("--once", action="store_true"); p.add_argument("--interval", type=float, default=20)
    agent_sub.add_parser("status")

    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            return serve_forever(args)
        if args.command == "admin":
            return run_admin(args)
        return run_agent(args)
    except (ContractError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def build_app(db_path):
    from .api import App
    from .store import Store
    store = Store(db_path)
    whatsapp = None
    if os.environ.get("WHATSAPP_APP_SECRET") and os.environ.get("WHATSAPP_VERIFY_TOKEN"):
        from .adapters.whatsapp import WhatsAppAdapter
        whatsapp = WhatsAppAdapter(store, os.environ["WHATSAPP_APP_SECRET"], os.environ["WHATSAPP_VERIFY_TOKEN"])
    return App(store, whatsapp)


def serve_forever(args):
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIServer, make_server

    class Server(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    app = build_app(args.db)
    with make_server(args.host, args.port, app, server_class=Server) as httpd:
        print(f"ARKOS relay en http://{args.host}:{args.port} (exponer solo detrás de HTTPS)", file=sys.stderr)
        httpd.serve_forever()


def run_admin(args):
    from .store import Store
    store = Store(args.db)
    try:
        if args.admin_command == "create-user":
            user_id = store.create_user(args.name)
            result = {"user_id": user_id, "token": store.issue_user_token(user_id)}
        elif args.admin_command == "issue-token":
            result = {"user_id": args.user, "token": store.issue_user_token(args.user, args.label)}
        else:
            store.bind_channel(args.user, "whatsapp", args.phone)
            result = {"user_id": args.user, "whatsapp": args.phone}
        print(json.dumps(result, indent=2))
        if "token" in result:
            print("Guardar el token ahora: no se vuelve a mostrar.", file=sys.stderr)
    finally:
        store.close()
    return 0


def _config(state_dir):
    path = state_dir / "agent.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_config(state_dir, config):
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "agent.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def run_agent(args):
    from . import agent as ag
    state_dir = args.state_dir
    config = _config(state_dir)
    if args.agent_command == "pair":
        paired = ag.pair(args.server, args.code, args.allow_insecure_localhost)
        ag.save_secret(state_dir / "device.token", paired["device_token"])
        config.update(server=args.server, device_id=paired["device_id"], device_name=paired["name"],
                      allow_insecure_localhost=args.allow_insecure_localhost)
        config.setdefault("roots", {})
        _save_config(state_dir, config)
        print(json.dumps({"device_id": paired["device_id"], "name": paired["name"]}, indent=2))
        return 0
    if args.agent_command == "allow-root":
        path = args.path.resolve(strict=True)
        if not path.is_dir():
            raise ValueError("Debe ser una carpeta existente")
        config.setdefault("roots", {})[args.name] = str(path)
        _save_config(state_dir, config)
        print(json.dumps(config["roots"], indent=2, ensure_ascii=False))
        return 0
    if not config.get("device_id"):
        raise ValueError("Primero vincular: agent pair --server URL --code CODIGO")
    journal = ag.Journal(state_dir / "journal.sqlite3")
    try:
        if args.agent_command == "status":
            print(json.dumps({"config": config, "pending": [dict(r) for r in journal.pending()]}, indent=2, ensure_ascii=False))
            return 0
        transport = ag.HttpTransport(config["server"], ag.load_secret(state_dir / "device.token"),
                                     allow_insecure_localhost=config.get("allow_insecure_localhost", False))
        executor = ag.Executor(state_dir / "outputs", config.get("roots"))
        worker = ag.Agent(transport, config["device_id"], journal, executor, log=lambda m: print(m, file=sys.stderr))
        delay = args.interval
        while True:
            try:
                stopped = worker.run_once()
                delay = args.interval
            except ag.TransportError as exc:
                stopped = None
                delay = min(delay * 2, 300)  # offline: back off, keep journal
                print(f"Sin conexión ({exc}); reintento en {delay:.0f}s", file=sys.stderr)
            except ag.ApiError as exc:
                if exc.status == 401:
                    print(worker.stopped, file=sys.stderr)
                    return 2
                print(f"Servidor: {exc}", file=sys.stderr)
                stopped, delay = None, min(delay * 2, 300)
            if args.once or stopped:
                return 0 if not stopped else 2
            time.sleep(delay)
    finally:
        journal.close()


if __name__ == "__main__":
    sys.exit(main())
