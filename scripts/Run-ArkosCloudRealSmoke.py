"""REAL Cloud test from the PC (paid). Prepared; run only with explicit approval.

Two modes, both inside the gateway's cumulative trial budget (USD 1 for the pilot):
  functional  (--turns 1..5, default 3): one short conversation with history.
  latency     (--latency-sample 20..80): independent one-message turns; reports every latency
              and p50/p95 (nearest rank). Fewer than 20 turns never produce a p95.
Preconditions are checked before anything is sent: Cloud ready (consent, verified terms, same
terms record as the gateway), REAL provider, and an open trial whose remaining budget covers
the planned turns at worst case. Stops at the first turn that is not ok; never retries. Turns
start at least --pace-seconds apart (default 3.5 s): each turn makes about 3 gateway requests and
the gateway allows 60 per address per minute, so a 60-turn sample takes about 4 minutes. The
report has states, costs and latencies only, never content.

  ARKOS_CLOUD_DEVICE_TOKEN=akc_… python scripts/Run-ArkosCloudRealSmoke.py \\
      --state-dir <estado-PC> --cloud-config <cloud-client.json> --confirm-paid-calls [--latency-sample 60]
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
SAMPLE_PROMPT = "Respondé solo con una oración breve: ¿qué hora del día es buena para revisar tareas?"
WORST_CASE_TURN_MICRO_USD = 6_000  # Haiku 5.5, 12.000 caracteres de entrada y 2.048 de salida (ver docs)


def percentile(values, pct):
    if len(values) < 20:
        return None
    ordered = sorted(values)
    return ordered[max(0, -(-pct * len(ordered) // 100) - 1)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--cloud-config", type=Path, required=True)
    parser.add_argument("--turns", type=int, default=3, choices=range(1, 6))
    parser.add_argument("--latency-sample", type=int, choices=range(20, 81), metavar="20..80")
    parser.add_argument("--pace-seconds", type=float, default=3.5,
                        help="Separación mínima entre inicios de turno (límite del gateway: 60 pedidos/min)")
    parser.add_argument("--report", type=Path, default=Path("cloud-smoke-report.json"))
    parser.add_argument("--confirm-paid-calls", action="store_true", help="Obligatorio: cada turno se factura")
    parser.add_argument("--allow-test-gateway", action="store_true", help=argparse.SUPPRESS)  # CI only, fake provider
    args = parser.parse_args(argv)
    if not args.confirm_paid_calls:
        parser.error("Falta --confirm-paid-calls: esta prueba hace llamadas facturadas.")
    token = os.environ.get("ARKOS_CLOUD_DEVICE_TOKEN", "")
    if not token:
        parser.error("Falta ARKOS_CLOUD_DEVICE_TOKEN (token del dispositivo, no la clave del proveedor).")
    if args.pace_seconds < 0:
        parser.error("--pace-seconds no puede ser negativo.")
    planned = args.latency_sample or args.turns
    link = CloudLink.from_file(args.state_dir, args.cloud_config, token)
    report = dict(mode="latency" if args.latency_sample else "functional", planned_turns=planned, pace_seconds=args.pace_seconds,
                  started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), turns=[], aborted=None)
    try:
        activation = link.activation(refresh=True)
        gateway = link.gateway_status(refresh=False) or {}
        trial = gateway.get("trial")
        report.update(activation=dict(state=activation["state"], test=activation["test"]), trial_before=trial,
                      terms=link.status()["terms"])
        if activation["state"] != "ready":
            report["aborted"] = "Cloud no está listo: " + activation["reason"]
        elif activation["test"] and not args.allow_test_gateway:
            report["aborted"] = "El gateway informa un proveedor de prueba: esto no es una prueba real."
        elif not trial and not activation["test"]:
            report["aborted"] = "El gateway no tiene una prueba con presupuesto acumulado abierta."
        elif trial and trial["remaining_micro_usd"] < planned * WORST_CASE_TURN_MICRO_USD:
            report["aborted"] = (f"Presupuesto de la prueba insuficiente para {planned} turnos en el peor caso "
                                 f"(quedan {trial['remaining_micro_usd']} µUSD).")
        if report["aborted"]:
            return finish(report, args.report, 2)
        history = []
        last_start = None
        for n in range(planned):
            if last_start is not None:
                time.sleep(max(0.0, args.pace_seconds - (time.monotonic() - last_start)))
            last_start = time.monotonic()
            prompt = SAMPLE_PROMPT if args.latency_sample else PROMPTS[n]
            rid = "smoke-" + uuid.uuid4().hex[:20]
            request = dict(v=1, request_id=rid, messages=[*history, dict(role="user", content=prompt)], timeout_s=60)
            started = time.monotonic()
            view = link.chat.start(request)
            while view["state"] == "waiting" and time.monotonic() - started < 75:
                time.sleep(0.1)
                view = link.chat.get(rid)
            latency = int((time.monotonic() - started) * 1000)
            response = view.get("response") or {}
            check = link.check(rid)
            report["turns"].append(dict(request_id=rid, state=view["state"], error_code=response.get("error_code"),
                                        latency_ms=latency, reply_chars=len(response.get("reply") or ""),
                                        proposals=len(response.get("proposals") or []),
                                        gateway_state=check.get("state"), charged_micro_usd=check.get("charged_micro_usd")))
            if view["state"] != "ok":
                report["aborted"] = f"Turno {rid} terminó en {view['state']}; no se reintenta."
                break
            if not args.latency_sample:
                history = [m for m in [*request["messages"], dict(role="assistant", content=response["reply"])]
                           if m["content"].strip()]
        ok = [t["latency_ms"] for t in report["turns"] if t["state"] == "ok"]
        report["latency_ms"] = dict(each=[t["latency_ms"] for t in report["turns"]], max=max(ok) if ok else None,
                                    p50=percentile(ok, 50), p95=percentile(ok, 95),
                                    note="Latencia vista desde la PC (incluye red y gateway). p50/p95 solo con 20 o más turnos.")
        report["total_charged_micro_usd"] = sum(t["charged_micro_usd"] or 0 for t in report["turns"])
        report["trial_after"] = (link.gateway_status(refresh=True) or {}).get("trial")
        return finish(report, args.report, 0 if not report["aborted"] else 1)
    finally:
        link.close()


def finish(report, path, code):
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report.get(k) for k in ("mode", "activation", "aborted", "total_charged_micro_usd")},
                     ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
