"""PC-side HTTP(S) transport to the ARKOS gateway, for CloudConversationProvider.

- https with certificate and hostname verification (system CAs, or an explicit CA file);
  plain http only for loopback, already enforced by ClientConfig.
- No proxies from the environment, no redirects, no retries.
- Separates "nothing left the PC" (TransportNotSent: DNS, refused, TLS handshake) from
  "sent, answer unknown" (any later failure), which the adapter reports as uncertain.
- Responses larger than the adapter's limit are cut and become an invalid response.
"""
import http.client
import ssl
from urllib.parse import urlsplit

from .adapter import MAX_RESPONSE_BYTES, TransportNotSent


class HttpTransport:
    def __init__(self, gateway_url, ca_file=None):
        parts = urlsplit(gateway_url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.path not in ("", "/"):
            raise ValueError("URL del gateway inválida")
        self.scheme, self.host, self.port = parts.scheme, parts.hostname, parts.port
        self.context = None
        if parts.scheme == "https":
            self.context = ssl.create_default_context(cafile=ca_file)
            self.context.minimum_version = ssl.TLSVersion.TLSv1_2

    def request(self, method, path, headers, body, timeout_s):
        if self.scheme == "https":
            conn = http.client.HTTPSConnection(self.host, self.port, timeout=timeout_s, context=self.context)
        else:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout_s)
        try:
            try:
                conn.connect()
            except OSError as exc:  # DNS, refused, unreachable, TLS handshake/verification
                raise TransportNotSent() from exc
            conn.request(method, path, body=bytes(body) if body else None, headers=dict(headers))
            response = conn.getresponse()
            data = response.read(MAX_RESPONSE_BYTES + 1)
            return response.status, data
        finally:
            conn.close()
