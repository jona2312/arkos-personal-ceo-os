"""ARKOS Cloud CLI. Nothing here sends conversation data or enables Cloud in the interface.

PC (consent; shows exactly what would be sent and to whom; accepting requires the code):
  python -m arkos_cloud consent --config cloud.json --state DIR [--accept CODE | --revoke]
Gateway server (one instance per ledger; provider key from the file in ARKOS_CLOUD_PROVIDER_KEY_FILE,
or ARKOS_CLOUD_PROVIDER_KEY; a real provider also needs a complete terms record):
  python -m arkos_cloud serve --gateway-config gateway.json --ledger L [--host H --port P]
                              [--tls-cert C --tls-key K | --behind-tls-proxy]
Gateway operator (works while the gateway runs; changes apply to the next request):
  python -m arkos_cloud token issue  --ledger L --user U     (prints the akc_ token once)
  python -m arkos_cloud token revoke --ledger L (--user U | --prefix HASHPREFIX)
  python -m arkos_cloud token list   --ledger L
  python -m arkos_cloud reconcile    --ledger L --user U --request-id R --charged MICRO_USD
  python -m arkos_cloud backup       --ledger L --out DIR [--keep 14]   (copia consistente en caliente)
"""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import threading

from .config import ClientConfig, ConfigError, GatewayConfig
from .consent import CONFIRM_CHARS, ConsentStore
from .ledger import Ledger, LedgerError


def _consent(args):
    try:
        config = ClientConfig.from_mapping(json.loads(args.config.read_text(encoding="utf-8")))
    except (OSError, ValueError, ConfigError) as exc:
        print(f"Configuración Cloud inválida: {exc}", file=sys.stderr)
        return 2
    store = ConsentStore(args.state)
    disclosure = config.disclosure
    if args.revoke:
        print("Consentimiento revocado." if store.revoke() else "No había consentimiento registrado.")
        return 0
    if args.accept is not None:
        try:
            store.grant(disclosure, args.accept)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print("Consentimiento registrado para esta configuración exacta.")
        return 0
    print(disclosure.summary())
    print(f"Gateway: {config.gateway_url}")
    state = "vigente" if store.valid_for(disclosure) else "no otorgado"
    print(f"Estado: {state}. Para aceptar, escribí el código: {disclosure.digest()[:CONFIRM_CHARS]}")
    return 0


def _operator(args):
    creating = args.command == "token" and args.action == "issue"
    if not creating and not args.ledger.exists():
        print("Ledger inexistente.", file=sys.stderr)
        return 2
    ledger = Ledger(args.ledger)
    try:
        if args.command == "token" and args.action == "issue":
            print(ledger.issue_token(args.user))
            print("Guardalo ahora: el gateway conserva solo su hash.", file=sys.stderr)
        elif args.command == "token" and args.action == "revoke":
            if args.prefix:
                ledger.revoke_prefix(args.prefix)
                print("Token revocado.")
            else:
                print(f"Tokens revocados: {ledger.revoke_user(args.user)}")
        elif args.command == "token":
            for row in ledger.tokens():
                print(f"{row['token_prefix']}  {row['user_id']}  {'revocado' if row['revoked'] else 'activo'}")
        else:
            row = ledger.reconcile(args.user, args.request_id, args.charged)
            print(f"{row['request_id']}: {row['state']}, cobrado {row['charged']} µUSD")
        return 0
    except (LedgerError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        ledger.close()


KEY_ENV = "ARKOS_CLOUD_PROVIDER_KEY"
KEY_FILE_ENV = "ARKOS_CLOUD_PROVIDER_KEY_FILE"
TEST_BASE_URL_ENV = "ARKOS_CLOUD_TEST_PROVIDER_URL"  # loopback fakes only; refused otherwise


def _provider_key():
    """Prefer a file readable only by the service user (systemd credential / Docker secret)."""
    path = os.environ.get(KEY_FILE_ENV, "")
    if path:
        file = Path(path)
        if os.name != "nt" and file.stat().st_mode & 0o077:
            raise ValueError(f"{KEY_FILE_ENV} no debe ser legible por otros usuarios (chmod 600 o 400).")
        key = file.read_text(encoding="utf-8").strip()
    else:
        key = os.environ.get(KEY_ENV, "")
    if not key:
        raise ValueError(f"Falta la credencial del proveedor: definí {KEY_FILE_ENV} (recomendado) o {KEY_ENV}.")
    return key


def _serve(args):
    from .gateway import CloudGateway
    from .provider_anthropic import AnthropicProvider
    from .server import GatewayServer
    try:
        config = GatewayConfig.from_mapping(json.loads(args.gateway_config.read_text(encoding="utf-8")))
    except (OSError, ValueError, ConfigError) as exc:
        print(f"Configuración del gateway inválida: {exc}", file=sys.stderr)
        return 2
    try:
        key = _provider_key()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        from . import terms
        record, terms_digest = terms.load(args.terms_record)
        verdict = terms.evaluate(record, config.disclosure)
        if verdict["problems"]:
            raise ValueError("Registro de condiciones inconsistente con la configuración:\n- " + "\n- ".join(verdict["problems"]))
        provider = AnthropicProvider(config.disclosure.model, key, base_url=os.environ.get(TEST_BASE_URL_ENV) or None,
                                     inference_geo=config.disclosure.region)
        if provider.mode == "real" and not verdict["ok"]:
            provider.close()
            raise ValueError("Proveedor real bloqueado: las condiciones no están verificadas. Pendiente:\n- "
                             + "\n- ".join(verdict["pending"]))
        gateway = CloudGateway(config, args.ledger, provider, terms_digest=terms_digest)
    except (RuntimeError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 3
    try:
        server = GatewayServer(gateway, args.host, args.port, args.tls_cert, args.tls_key, args.behind_tls_proxy,
                               trusted_proxy=args.trusted_proxy)
    except (OSError, ValueError) as exc:
        gateway.close()
        print(str(exc), file=sys.stderr)
        return 3
    stop = threading.Event()
    for name in ("SIGTERM", "SIGINT"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: stop.set())
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    thread.start()
    print(json.dumps({"listening": server.url}), flush=True)
    try:
        while not stop.wait(0.5):
            pass
    finally:
        server.shutdown()
        server.server_close()
        gateway.close()
    return 0


def _backup(args):
    """Consistent online copy (SQLite backup API) + integrity check; keeps the newest N copies."""
    import sqlite3
    import time
    if not args.ledger.exists():
        print("Ledger inexistente.", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / time.strftime("ledger-%Y%m%dT%H%M%SZ.sqlite3", time.gmtime())
    source = sqlite3.connect(f"file:{args.ledger}?mode=ro", uri=True)
    copy = sqlite3.connect(target)
    try:
        source.backup(copy)
        status = copy.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        copy.close()
        source.close()
    if status != "ok":
        target.unlink()
        print(f"Copia descartada: integrity_check={status}", file=sys.stderr)
        return 1
    if os.name != "nt":
        target.chmod(0o600)
    copies = sorted(args.out.glob("ledger-*.sqlite3"))
    for old in copies[:-args.keep] if args.keep > 0 else []:
        old.unlink()
    print(target)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="arkos_cloud")
    sub = parser.add_subparsers(dest="command", required=True)
    consent = sub.add_parser("consent")
    consent.add_argument("--config", type=Path, required=True)
    consent.add_argument("--state", type=Path, required=True)
    group = consent.add_mutually_exclusive_group()
    group.add_argument("--accept", metavar="CODE")
    group.add_argument("--revoke", action="store_true")
    token = sub.add_parser("token")
    token.add_argument("action", choices=("issue", "revoke", "list"))
    token.add_argument("--ledger", type=Path, required=True)
    token.add_argument("--user")
    token.add_argument("--prefix")
    serve = sub.add_parser("serve")
    serve.add_argument("--gateway-config", type=Path, required=True)
    serve.add_argument("--ledger", type=Path, required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--tls-cert")
    serve.add_argument("--tls-key")
    serve.add_argument("--behind-tls-proxy", action="store_true")
    serve.add_argument("--trusted-proxy", help="IP del proxy TLS local cuyo X-Forwarded-For se usa para el límite por dirección")
    serve.add_argument("--terms-record", type=Path, help="Registro de condiciones (por defecto config/cloud-terms-record.json)")
    backup = sub.add_parser("backup")
    backup.add_argument("--ledger", type=Path, required=True)
    backup.add_argument("--out", type=Path, required=True)
    backup.add_argument("--keep", type=int, default=14)
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--ledger", type=Path, required=True)
    reconcile.add_argument("--user", required=True)
    reconcile.add_argument("--request-id", required=True)
    reconcile.add_argument("--charged", type=int, required=True)
    args = parser.parse_args(argv)
    if args.command == "consent":
        return _consent(args)
    if args.command == "serve":
        return _serve(args)
    if args.command == "backup":
        return _backup(args)
    if args.command == "token" and args.action == "issue" and not args.user:
        parser.error("token issue requiere --user")
    if args.command == "token" and args.action == "revoke" and bool(args.user) == bool(args.prefix):
        parser.error("token revoke requiere --user o --prefix")
    return _operator(args)


if __name__ == "__main__":
    sys.exit(main())
