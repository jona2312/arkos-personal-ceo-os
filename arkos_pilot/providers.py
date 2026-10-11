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
    Cloud is deliberately unavailable until its own acceptance is complete.
    Metadata describes intended processing, not proof of OS-level isolation.
    """
    if mode == 'cloud':
        raise ValueError('Cloud no disponible: falta integrar consentimiento, cuotas y proveedor.')
    if mode not in ('hermes', 'synthetic'):
        raise ValueError('Modo de conversación no soportado.')
    if bridge is None:
        return ProviderSelection(None, 'unconfigured', 'unconfigured')
    if not callable(getattr(bridge, 'converse', None)):
        raise ValueError('El proveedor no implementa el contrato de conversación.')
    return ProviderSelection(bridge, mode, 'local' if mode == 'hermes' else 'synthetic')
