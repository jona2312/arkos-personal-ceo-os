"""Minimal REAL Cloud test from the PC (paid). Prepared; run only with explicit approval.

Preconditions are checked before anything is sent: Cloud configured, consent granted in this
state dir, gateway reports a REAL provider with the same disclosure and terms record, and the
terms record is complete (no pending checks). At most 5 turns; stops at the first turn that is
not ok and never retries. The report has states, costs and latency only, never content.

  ARKOS_CLOUD_DEVICE_TOKEN=akc_… python scripts/Run-ArkosCloudRealSmoke.py \\
      --state-dir <estado-PC> --cloud-config <cloud-client.json> --confirm-paid-calls
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arkos_pilot.cloud_link import CloudLink

PROMPTS = (
    "Hola. Respondé en una oración: ¿qué podés hacer y qué no en este modo?",
    "Proponé una nota breve para recordar revisar el presupuesto del piloto el viernes.",
    "Resumí en una línea lo que acordamos.",
    "¿Qué datos de esta conversación se enviaron fuera de mi PC?",
    "Gracias, eso es todo.",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--cloud-config", type=Path, required=True)
    parser.add_argument("--turns", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--report", type=Path, default=Path("cloud-smoke-report.json"))
    parser.add_argument("--confirm-paid-calls", action="store_true", help="Obligatorio: cada turno se factura")
    parser.add_argument("--allow-test-gateway", action="store_true", help=argparse.SUPPRESS)  # CI only, fake provider
    args = parser.parse_args(argv)
    if not args.confirm_paid_calls:
        parser.error("Falta --confirm-paid-calls: esta prueba hace llamadas facturadas.")
    token = os.environ.get("ARKOS_CLOUD_DEVICE_TOKEN", "")
    if not token:
        parser.error("Falta ARKOS_CLOUD_DEVICE_TOKEN (token del dispositivo, no la clave del proveedor).")
    link = CloudLink.from_file(args.state_dir, args.cloud_config, token)
    report = dict(started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), turns=[], aborted=None)
    try:
        activation = link.activation(refresh=True)
        report["activation"] = dict(state=activation["state"], test=activation["test"])
        report["terms"] = link.status()["terms"]
        if activation["state"] != "ready":
            report["aborted"] = "Cloud no está listo: " + activation["reason"]
        elif activation["test"] and not args.allow_test_gateway:
            report["aborted"] = "El gateway informa un proveedor de prueba: esto no es una prueba real."
        if report["aborted"]:
            return finish(report, args.report, 2)
        history = []
        for prompt in PROMPTS[:args.turns]:
            rid = "smoke-" + uuid.uuid4().hex[:20]
            request = dict(v=1, request_id=rid, messages=[*history, dict(role="user", content=prompt)], timeout_s=60)
            # Through the same Conversations the screen uses: consent, terms and Cloud-only history apply.
            started = time.monotonic()
            view = link.chat.start(request)
            while view["state"] == "waiting" and time.monotonic() - started < 75:
                time.sleep(0.25)
                view = link.chat.get(rid)
            response = view.get("response") or {}
            check = link.check(rid)
            report["turns"].append(dict(request_id=rid, state=view["state"], error_code=response.get("error_code"),
                                        latency_ms=int((time.monotonic() - started) * 1000),
                                        reply_chars=len(response.get("reply") or ""),
                                        proposals=len(response.get("proposals") or []),
                                        gateway_state=check.get("state"), charged_micro_usd=check.get("charged_micro_usd")))
            if view["state"] != "ok":
                report["aborted"] = f"Turno {rid} terminó en {view['state']}; no se reintenta."
                break
            history = [*request["messages"], dict(role="assistant", content=response["reply"])]
            history = [m for m in history if m["content"].strip()]
        report["total_charged_micro_usd"] = sum(t["charged_micro_usd"] or 0 for t in report["turns"])
        return finish(report, args.report, 0 if not report["aborted"] else 1)
    finally:
        link.close()


def finish(report, path, code):
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("activation", "aborted", "total_charged_micro_usd")}, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
