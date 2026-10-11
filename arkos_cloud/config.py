"""Explicit Cloud configuration. Strict: unknown keys, secrets and implicit defaults are refused.

The client config never contains a provider key. It may name a gateway URL; the gateway
holds the provider credential server-side (see docs/CLOUD_ADAPTER.md).
"""
from dataclasses import dataclass, asdict
import hashlib
import ipaddress
import json
import re
from urllib.parse import urlsplit

from arkos_hermes import contract as c

# What leaves the PC. Part of the consent digest: changing the wording requires new consent.
DATA_SENT = ("El texto de los mensajes de esta conversación (historial acotado) y el pedido actual. "
             "No se envían archivos, tareas, notas guardadas, credenciales ni datos del sistema.")
_SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|sk-ant-|Bearer\s|ak[udrc]_[A-Za-z0-9_-]{8,}|-----BEGIN)", re.I)
_SECRET_KEY = re.compile(r"(key|secret|token|password|credential)", re.I)
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,79}$")


class ConfigError(ValueError):
    pass


def _strict(data, fields, label):
    if not isinstance(data, dict):
        raise ConfigError(f"{label}: se esperaba un objeto")
    for key, value in data.items():
        if key not in fields and _SECRET_KEY.search(str(key)):
            raise ConfigError(f"{label}: no se aceptan claves ni secretos en la configuración ({key})")
        if isinstance(value, str) and _SECRET.search(value):
            raise ConfigError(f"{label}: valor con forma de credencial en {key}")
    unknown, missing = set(data) - set(fields), set(fields) - set(data)
    if unknown or missing:
        # Explicit: every field must be stated; nothing is defaulted silently.
        raise ConfigError(f"{label}: campos desconocidos {sorted(unknown)} o faltantes {sorted(missing)}")


def _int(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ConfigError(f"{label} debe ser entero entre {low} y {high}")
    return value


def _name(value, label):
    if not isinstance(value, str) or not _NAME.match(value):
        raise ConfigError(f"{label} inválido")
    return value


@dataclass(frozen=True)
class Disclosure:
    """What the person consents to. Shared by client and gateway; its digest binds both."""
    policy_version: str
    provider: str
    model: str
    region: str
    provider_retention_days: int
    gateway_retention_hours: int
    max_input_chars: int
    max_output_tokens: int

    FIELDS = ("policy_version", "provider", "model", "region", "provider_retention_days",
              "gateway_retention_hours", "max_input_chars", "max_output_tokens")

    @classmethod
    def from_mapping(cls, data):
        _strict(data, cls.FIELDS, "disclosure")
        return cls(policy_version=_name(data["policy_version"], "policy_version"),
                   provider=_name(data["provider"], "provider"), model=_name(data["model"], "model"),
                   region=_name(data["region"], "region"),
                   provider_retention_days=_int(data["provider_retention_days"], 0, 3650, "provider_retention_days"),
                   gateway_retention_hours=_int(data["gateway_retention_hours"], 0, 72, "gateway_retention_hours"),
                   max_input_chars=_int(data["max_input_chars"], 1, c.MAX_HISTORY_CHARS, "max_input_chars"),
                   max_output_tokens=_int(data["max_output_tokens"], 16, 4096, "max_output_tokens"))

    def as_dict(self):
        body = asdict(self)
        body["data_sent"] = DATA_SENT
        return body

    def digest(self):
        raw = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def summary(self):
        """Human-readable text shown before consent. Plain text; the caller escapes it."""
        return (f"Proveedor: {self.provider} · modelo {self.model} · región {self.region}\n"
                f"Datos enviados: {DATA_SENT}\n"
                f"Retención del proveedor: {self.provider_retention_days} días (según su política)\n"
                f"Retención en el gateway ARKOS: {self.gateway_retention_hours} h para no repetir cobros\n"
                f"Límites: {self.max_input_chars} caracteres de entrada, {self.max_output_tokens} tokens de salida\n"
                f"Política {self.policy_version}. Cancelar no garantiza que el proveedor no haya procesado el pedido.")


@dataclass(frozen=True)
class ClientConfig:
    gateway_url: str
    timeout_s: int
    disclosure: Disclosure

    @classmethod
    def from_mapping(cls, data):
        _strict(data, ("gateway_url", "timeout_s", "disclosure"), "cloud")
        url = data["gateway_url"]
        parts = urlsplit(url) if isinstance(url, str) else None
        if not parts or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ConfigError("gateway_url inválida")
        loopback = parts.hostname == "localhost"
        try:
            loopback = loopback or ipaddress.ip_address(parts.hostname).is_loopback
        except ValueError:
            pass
        if parts.scheme != "https" and not (parts.scheme == "http" and loopback):
            raise ConfigError("gateway_url debe usar https (http solo en loopback para pruebas)")
        return cls(gateway_url=url.rstrip("/"),
                   timeout_s=_int(data["timeout_s"], c.MIN_TIMEOUT, c.MAX_TIMEOUT, "timeout_s"),
                   disclosure=Disclosure.from_mapping(data["disclosure"]))


@dataclass(frozen=True)
class GatewayConfig:
    """Server side only. Prices in micro-USD per million tokens; budgets in micro-USD per UTC day.

    Prices must be the ones actually billed, multipliers included (e.g. inference_geo).
    long_context_threshold_tokens > 0 applies the long_* prices to a whole request whose
    input exceeds it (Claude Haiku 5.5 bills prompts over 100,000 tokens that way); 0 = no tier.
    """
    disclosure: Disclosure
    input_micro_usd_per_mtok: int
    output_micro_usd_per_mtok: int
    long_context_threshold_tokens: int
    long_input_micro_usd_per_mtok: int
    long_output_micro_usd_per_mtok: int
    per_user_daily_micro_usd: int
    global_daily_micro_usd: int

    @classmethod
    def from_mapping(cls, data):
        fields = ("disclosure", "input_micro_usd_per_mtok", "output_micro_usd_per_mtok",
                  "long_context_threshold_tokens", "long_input_micro_usd_per_mtok",
                  "long_output_micro_usd_per_mtok", "per_user_daily_micro_usd", "global_daily_micro_usd")
        _strict(data, fields, "gateway")
        cfg = cls(disclosure=Disclosure.from_mapping(data["disclosure"]),
                  input_micro_usd_per_mtok=_int(data["input_micro_usd_per_mtok"], 1, 10**9, "precio entrada"),
                  output_micro_usd_per_mtok=_int(data["output_micro_usd_per_mtok"], 1, 10**9, "precio salida"),
                  long_context_threshold_tokens=_int(data["long_context_threshold_tokens"], 0, 10**7, "umbral contexto largo"),
                  long_input_micro_usd_per_mtok=_int(data["long_input_micro_usd_per_mtok"], 1, 10**9, "precio entrada largo"),
                  long_output_micro_usd_per_mtok=_int(data["long_output_micro_usd_per_mtok"], 1, 10**9, "precio salida largo"),
                  per_user_daily_micro_usd=_int(data["per_user_daily_micro_usd"], 0, 10**10, "presupuesto por usuario"),
                  global_daily_micro_usd=_int(data["global_daily_micro_usd"], 0, 10**11, "presupuesto global"))
        if cfg.per_user_daily_micro_usd > cfg.global_daily_micro_usd:
            raise ConfigError("El presupuesto por usuario no puede superar el global")
        if (cfg.long_input_micro_usd_per_mtok < cfg.input_micro_usd_per_mtok
                or cfg.long_output_micro_usd_per_mtok < cfg.output_micro_usd_per_mtok):
            raise ConfigError("Los precios de contexto largo no pueden ser menores que los base")
        return cfg
