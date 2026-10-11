"""Synthetic provider and in-process transport for the Cloud adapter. No network, no keys."""
import json
import threading

from arkos_cloud.adapter import TransportNotSent
from arkos_cloud.config import ClientConfig, GatewayConfig
from arkos_cloud.gateway import ProviderLost, ProviderNotSent, ProviderRejected, ProviderResult, token_hash

TOKEN_A = "akc_" + "a" * 40
TOKEN_B = "akc_" + "b" * 40
DISCLOSURE = dict(policy_version="2026-10-11", provider="synthetic-llm", model="synthetic-model-1",
                  region="test", provider_retention_days=30, gateway_retention_hours=24,
                  max_input_chars=12000, max_output_tokens=1024)


def client_config(**disclosure):
    return ClientConfig.from_mapping(dict(gateway_url="https://gateway.arkos.invalid", timeout_s=30,
                                          disclosure=dict(DISCLOSURE, **disclosure)))


def gateway_config(user_budget=100_000, global_budget=1_000_000, **disclosure):
    return GatewayConfig.from_mapping(dict(disclosure=dict(DISCLOSURE, **disclosure),
                                           input_micro_usd_per_mtok=1_000_000, output_micro_usd_per_mtok=5_000_000,
                                           per_user_daily_micro_usd=user_budget, global_daily_micro_usd=global_budget))


TOKENS = {token_hash(TOKEN_A): "user-a", token_hash(TOKEN_B): "user-b"}


class SimulatedProvider:
    """behaviour: ok | lost | not_sent | rejected | slow | no_usage | huge, or a callable."""

    def __init__(self, behaviour="ok", text="Hola, soy una respuesta sintética.", hold=None):
        self.behaviour, self.text = behaviour, text
        self.calls = []
        self.hold = hold            # threading.Event the provider waits on before answering
        self.entered = threading.Event()
        self.observe = None         # callable run inside the call (e.g. to inspect the ledger)
        self.lock = threading.Lock()

    def complete(self, system, messages, max_output_tokens, timeout_s, cancel_event):
        with self.lock:
            self.calls.append(dict(system=system, messages=messages, max_output_tokens=max_output_tokens))
        if self.observe:
            self.observe()
        self.entered.set()
        if self.hold is not None:
            self.hold.wait(10)
        b = self.behaviour
        if callable(b):
            return b()
        if b == "lost":
            raise ProviderLost()
        if b == "not_sent":
            raise ProviderNotSent()
        if b == "rejected":
            raise ProviderRejected()
        if b == "no_usage":
            return ProviderResult(self.text, None, None)
        if b == "huge":
            return ProviderResult("x" * (max_output_tokens * 16 + 1), 100, max_output_tokens)
        return ProviderResult(self.text, 120, 40)


class InProcessTransport:
    """fault: None | not_sent | drop_response | garbage | oversize, applied to POST /v1/conversations."""

    def __init__(self, gateway, fault=None, delay=None):
        self.gateway, self.fault, self.delay = gateway, fault, delay
        self.requests = []
        self.lock = threading.Lock()

    def request(self, method, path, headers, body, timeout_s):
        with self.lock:
            self.requests.append(dict(method=method, path=path, headers=dict(headers), body=bytes(body)))
        is_post = method == "POST" and path == "/v1/conversations"
        if is_post and self.fault == "not_sent":
            raise TransportNotSent()
        if is_post and self.delay is not None:
            self.delay.wait(10)
        status, data = self.gateway.dispatch(method, path, headers, body)
        if is_post and self.fault == "drop_response":
            raise ConnectionResetError("simulated loss after the gateway processed the request")
        if is_post and self.fault == "garbage":
            return 502, b"<html>bad gateway</html>"
        if is_post and self.fault == "oversize":
            return 200, b" " * (256 * 1024 + 1)
        return status, json.dumps(data, ensure_ascii=False).encode("utf-8")

    def posts(self):
        return [r for r in self.requests if r["method"] == "POST" and r["path"] == "/v1/conversations"]
