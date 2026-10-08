"""Manual acceptance CLI. Prints JSON; never stores the conversation or proposals."""
import argparse
import json
import sys
import uuid

from .bridge import HermesBridge


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(prog="arkos_hermes", description="Puente de conversación ARKOS -> Hermes (sin herramientas)")
    parser.add_argument("--hermes-python", required=True, help="Python privado de Hermes")
    parser.add_argument("--hermes-source", required=True, help="Checkout de Hermes que usa ese Python")
    parser.add_argument("--hermes-home", required=True, help="Perfil dedicado del puente (sin plugins)")
    parser.add_argument("--model", default="")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("message", help="Mensaje del usuario")
    args = parser.parse_args(argv)
    bridge = HermesBridge(args.hermes_python, args.hermes_source, args.hermes_home, args.model)
    result = bridge.converse({"v": 1, "request_id": "cli-" + uuid.uuid4().hex[:12],
                              "messages": [{"role": "user", "content": args.message}], "timeout_s": args.timeout})
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
