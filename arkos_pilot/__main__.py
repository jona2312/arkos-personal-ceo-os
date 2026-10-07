import argparse
import json
import os
from pathlib import Path
from .catalog import inventory, propose
from .core import Queue, clip_payload


def main():
    parser = argparse.ArgumentParser(description="ARKOS: piloto local con acciones aprobadas")
    default = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "ArkosPilot"
    parser.add_argument("--state-dir", type=Path, default=default)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    p = commands.add_parser("propose"); p.add_argument("goal")
    p = commands.add_parser("note"); p.add_argument("text")
    p = commands.add_parser("clip"); p.add_argument("source"); p.add_argument("--start", type=float, default=0); p.add_argument("--duration", type=float, required=True)
    commands.add_parser("list")
    p = commands.add_parser("show"); p.add_argument("id")
    p = commands.add_parser("approve"); p.add_argument("id"); p.add_argument("fingerprint"); p.add_argument("--hours", type=float, default=24)
    p = commands.add_parser("cancel"); p.add_argument("id")
    commands.add_parser("run-next")
    commands.add_parser("recover-interrupted")
    args = parser.parse_args()
    queue = None
    try:
        if args.command == "doctor":
            result = {"state_dir": str(args.state_dir), "tools": inventory()}
        elif args.command == "propose":
            result = propose(args.goal)
        else:
            queue = Queue(args.state_dir)
            if args.command == "note": result = queue.add({"action": "note", "text": args.text})
            elif args.command == "clip": result = queue.add(clip_payload(args.source, args.start, args.duration))
            elif args.command == "list": result = queue.list()
            elif args.command == "show": result = queue.get(args.id)
            elif args.command == "approve": result = queue.approve(args.id, args.fingerprint, args.hours)
            elif args.command == "cancel": result = queue.cancel(args.id)
            elif args.command == "run-next": result = queue.run_next()
            else:
                queue.recover(); result = {"status": "Revisa tareas bloqueadas antes de volver a aprobar"}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + "\n")
    finally:
        if queue: queue.close()


if __name__ == "__main__":
    main()
