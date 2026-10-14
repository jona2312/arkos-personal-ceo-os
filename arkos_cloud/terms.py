"""Provider-terms verification record. A real provider is usable only when this record says so.

`terms_verified: true` in the disclosure is necessary but never sufficient: the record must
(1) declare exactly what the consent screen shows, (2) cite official public sources read
recently, (3) have every account/contract check confirmed with evidence by a named person,
(4) have no open discrepancy, and (5) not be expired. Anything missing keeps Cloud on the
fake provider only. The record is public data: no keys, account ids or personal data.
"""
from datetime import date
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

SCHEMA = "arkos.cloud.terms/1"
OFFICIAL_HOSTS = {"platform.claude.com", "docs.claude.com", "support.claude.com", "privacy.claude.com",
                  "www.anthropic.com", "anthropic.com", "trust.anthropic.com"}
MAX_SOURCE_AGE_DAYS = 90
DEFAULT_PATH = Path(__file__).resolve().parents[1] / "config" / "cloud-terms-record.json"
# Disclosure field -> key in record["declared"]; they must be equal.
DECLARED = {"provider": "provider", "model": "model", "region": "inference_geo",
            "provider_retention_days": "retention_days_max", "provider_flagged_retention_days": "flagged_retention_days_max",
            "provider_trains_on_data": "trains_on_customer_content", "provider_storage_region": "storage_region"}


class TermsError(ValueError):
    pass


def load(path=None):
    path = Path(path or DEFAULT_PATH)
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise TermsError("Registro de condiciones con esquema desconocido")
    return data, hashlib.sha256(raw).hexdigest()


def _day(value, label, problems):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        problems.append(f"{label}: fecha inválida")
        return None


def evaluate(record, disclosure, today=None):
    """Returns dict(ok, problems, pending, summary). Never raises for content problems."""
    today = today or date.today()
    problems, pending = [], []
    declared = record.get("declared") if isinstance(record.get("declared"), dict) else {}
    for field, key in DECLARED.items():
        if declared.get(key) != getattr(disclosure, field):
            problems.append(f"Lo declarado ({key}={declared.get(key)!r}) no coincide con el consentimiento "
                            f"({field}={getattr(disclosure, field)!r})")
    sources = record.get("public_sources") if isinstance(record.get("public_sources"), list) else []
    if not sources:
        problems.append("Sin fuentes públicas")
    covered = set()
    for source in sources:
        url = source.get("url", "") if isinstance(source, dict) else ""
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in OFFICIAL_HOSTS:
            problems.append(f"Fuente no oficial o sin https: {url!r}")
            continue
        read_on = _day(source.get("retrieved_on"), url, problems)
        if read_on and (today - read_on).days > MAX_SOURCE_AGE_DAYS:
            problems.append(f"Fuente leída hace más de {MAX_SOURCE_AGE_DAYS} días: {url}")
        if source.get("read_directly") is not True:
            pending.append(f"Leer directamente la fuente oficial: {url}")
        covered.update(source.get("supports") or [])
    for key in DECLARED.values():
        if key not in covered:
            problems.append(f"Ninguna fuente respalda {key}")
    for check in record.get("account_checks") or []:
        done = (isinstance(check, dict) and check.get("status") == "confirmed" and check.get("evidence")
                and check.get("confirmed_by") and _day(check.get("confirmed_on"), check.get("id", "?"), problems))
        if not done:
            pending.append(f"Comprobación de cuenta/contrato: {check.get('item', check) if isinstance(check, dict) else check}")
    for issue in record.get("discrepancies") or []:
        if not isinstance(issue, dict) or issue.get("status") != "resolved":
            pending.append(f"Discrepancia abierta: {issue.get('summary', issue) if isinstance(issue, dict) else issue}")
    valid_until = _day(record.get("valid_until"), "valid_until", problems)
    if valid_until and today > valid_until:
        problems.append("El registro de condiciones venció: hay que revisar las fuentes otra vez")
    if not getattr(disclosure, "terms_verified", False):
        pending.append("terms_verified sigue en false (se cambia recién cuando no queda nada pendiente)")
    reviewed = record.get("reviewed_on")
    return dict(ok=not problems and not pending, problems=problems, pending=pending,
                summary=dict(reviewed_on=reviewed, valid_until=record.get("valid_until"),
                             sources=len(sources), account_checks=len(record.get("account_checks") or []),
                             pending=len(pending), problems=len(problems)))
