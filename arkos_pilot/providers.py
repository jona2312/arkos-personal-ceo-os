"""Conversation provider selection, not an executor or network sandbox.

The v1 wire contract remains in arkos_hermes.contract for compatibility with
Hermes' private Python. Every future adapter must implement that same contract.
Only trusted application code may supply a bridge; HTTP/model input cannot.
"""
from dataclasses import dataclass
from threading import Event
from typing import Protocol


class ConversationProvider(Protocol):
    def converse(self, request: dict, cancel_event: Event | None = None) -> dict:
        """Return a validated v1 response; honour timeout and cancellation.

        Proposals are data only. This method has no authority to approve or
        execute tasks. The caller still validates every returned response.
        """
        ...


@dataclass(frozen=True)
class ProviderSelection:
    bridge: ConversationProvider | None
    mode: str
    processing: str


def select_provider(bridge=None, mode='hermes'):
    """Resolve one explicitly configured provider, without probing or fallback.

    'hermes' is the existing public mode name for the local adapter. 'synthetic'
    is an explicitly injected test adapter, never an implicit offline fallback.
    Cloud is accepted only as a CloudSessionGuard, which enforces consent, test-only activation
    while provider terms are unverified, and Cloud-only history.
    Metadata describes intended processing, not proof of OS-level isolation.
    """
    if mode == 'cloud':
        # Only the guarded Cloud session (consent, activation rules, Cloud-only history) can be
        # selected as Cloud; a bare adapter or any other object is refused. Never a fallback.
        from .cloud_link import CloudSessionGuard
        if not isinstance(bridge, CloudSessionGuard):
            raise ValueError('Cloud no disponible: requiere la sesión Cloud con consentimiento y límites.')
        return ProviderSelection(bridge, 'cloud', 'cloud')
    if mode not in ('hermes', 'synthetic'):
        raise ValueError('Modo de conversación no soportado.')
    if bridge is None:
        return ProviderSelection(None, 'unconfigured', 'unconfigured')
    if not callable(getattr(bridge, 'converse', None)):
        raise ValueError('El proveedor no implementa el contrato de conversación.')
    return ProviderSelection(bridge, mode, 'local' if mode == 'hermes' else 'synthetic')
