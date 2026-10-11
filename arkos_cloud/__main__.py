"""Consent CLI. Shows exactly what would be sent and to whom; accepting requires typing the code.

  python -m arkos_cloud consent --config cloud.json --state DIR            (show)
  python -m arkos_cloud consent --config cloud.json --state DIR --accept CODE
  python -m arkos_cloud consent --config cloud.json --state DIR --revoke
Nothing here sends data or enables Cloud in the interface.
"""
import argparse
import json
from pathlib import Path
import sys

from .config import ClientConfig, ConfigError
from .consent import CONFIRM_CHARS, ConsentStore


def main(argv=None):
    parser = argparse.ArgumentParser(prog="arkos_cloud")
    sub = parser.add_subparsers(dest="command", required=True)
    consent = sub.add_parser("consent")
    consent.add_argument("--config", type=Path, required=True)
    consent.add_argument("--state", type=Path, required=True)
    group = consent.add_mutually_exclusive_group()
    group.add_argument("--accept", metavar="CODE")
    group.add_argument("--revoke", action="store_true")
    args = parser.parse_args(argv)
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


if __name__ == "__main__":
    sys.exit(main())
