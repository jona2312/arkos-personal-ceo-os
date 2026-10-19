"""Gateway-side provider transport on the official Anthropic Python SDK (server only).

One Messages API request per call, never retried: max_retries=0 because every retry could
be billed again; the gateway ledger is the only idempotency authority. Sent: the contract's
system prompt, the bounded conversation, max_tokens (which also bounds billed reasoning) and
effort. Never sent: tool definitions or tool selection, cache_control, streaming, fallbacks.

Error mapping (ambiguous -> uncertain, never retried):
- connect error / connect timeout (nothing reached the API)      -> ProviderNotSent
- HTTP 4xx (invalid request, auth, permission, rate limit)        -> ProviderRejected
- read timeout, reset, 5xx/529, unreadable response              -> ProviderLost
"""
import ipaddress
from urllib.parse import urlsplit

from .gateway import ProviderLost, ProviderNotSent, ProviderRejected, ProviderResult

DEFAULT_EFFORT = "low"


def _loopback_http(url):
    parts = urlsplit(url)
    if parts.scheme != "http" or not parts.hostname:
        return False
    if parts.hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(parts.hostname).is_loopback
    except ValueError:
        return False


class AnthropicProvider:
    def __init__(self, model, api_key, base_url=None, effort=DEFAULT_EFFORT, sdk=None, inference_geo="global"):
        """base_url is only for local fakes in tests (http on loopback); production uses the SDK default."""
        if base_url is not None and not _loopback_http(base_url):
            raise ValueError("base_url solo se admite en loopback para pruebas")
        if not isinstance(api_key, str) or not api_key:
            raise ValueError("Falta la credencial del proveedor en el servidor")
        if effort not in ("low", "medium", "high"):
            raise ValueError("effort no permitido para el piloto")
        if inference_geo not in ("global", "us"):
            raise ValueError("inference_geo debe ser global o us (lo declarado en el consentimiento)")
        self.inference_geo = inference_geo
        if sdk is None:
            try:
                import anthropic as sdk
            except ImportError as exc:  # pragma: no cover - depends on the server image
                raise RuntimeError("Instalá requirements-cloud.txt en el servidor del gateway") from exc
        self._sdk = sdk
        self.model, self.effort = model, effort
        # A loopback base_url can only reach a local fake: the gateway reports it as a test.
        self.mode = "test" if base_url is not None else "real"
        self._client = sdk.Anthropic(api_key=api_key, base_url=base_url, max_retries=0)

    def close(self):
        self._client.close()

    def __repr__(self):
        return f"AnthropicProvider(model={self.model!r})"

    def complete(self, system, messages, max_output_tokens, timeout_s, cancel_event):
        sdk = self._sdk
        if cancel_event is not None and cancel_event.is_set():
            raise ProviderNotSent()
        try:
            response = self._client.messages.create(
                model=self.model, max_tokens=max_output_tokens, system=system,
                messages=[{"role": m["role"], "content": m["content"]} for m in messages],
                output_config={"effort": self.effort}, inference_geo=self.inference_geo, timeout=float(timeout_s))
        except sdk.APIConnectionError as exc:  # includes APITimeoutError
            cause = type(exc.__cause__).__name__ if exc.__cause__ is not None else ""
            if cause in ("ConnectError", "ConnectTimeout"):
                raise ProviderNotSent() from None
            raise ProviderLost() from None
        except sdk.APIStatusError as exc:
            if 400 <= exc.status_code < 500 and exc.status_code not in (408, 409):
                raise ProviderRejected() from None
            raise ProviderLost() from None
        except Exception:
            raise ProviderLost() from None
        try:
            usage = response.usage
            tokens_in = (usage.input_tokens + (usage.cache_creation_input_tokens or 0)
                         + (usage.cache_read_input_tokens or 0))
            tokens_out = usage.output_tokens
            text = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
        except Exception:
            raise ProviderLost() from None
        # The declared geography must be the one that served the request: a "us" promise answered
        # elsewhere is discarded (it is still billed). "global" accepts any reported value.
        served = getattr(usage, "inference_geo", None)
        if self.inference_geo == "us" and served != "us":
            return ProviderResult("", tokens_in, tokens_out)
        # refusal / max_tokens: billed per usage; the gateway decides what to show.
        return ProviderResult(text if response.stop_reason != "refusal" else "", tokens_in, tokens_out)
