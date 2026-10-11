"""Optional Cloud conversation for the task center. Off unless trusted code configures it.

Activation rules, checked before every turn (nothing is sent otherwise):
- the gateway answers and reports the same disclosure digest the screen shows;
- a real provider requires disclosure.terms_verified; with unverified terms only a gateway
  that reports a test provider (local fake) can be used;
- the person accepted that exact disclosure (consent bound to its digest).
History rule: a Cloud turn may only carry earlier turns of this same Cloud session, so a
local conversation is never forwarded to Cloud by switching modes.
"""
import json
from pathlib import Path
import threading
import time

from arkos_hermes import contract as c
from arkos_cloud.adapter import CloudConversationProvider
from arkos_cloud.config import ClientConfig
from arkos_cloud.consent import CONFIRM_CHARS, ConsentStore
from arkos_cloud.http_transport import HttpTransport

from .chat import ChatError, Conversations

STATUS_TTL_S = 5.0


class CloudSessionGuard:
    """The only object arkos_pilot.providers accepts as a Cloud provider."""
    processing = 'cloud'

    def __init__(self, link):
        self.link = link

    def converse(self, request, cancel_event=None):
        rid = request.get('request_id') if isinstance(request, dict) else None
        activation = self.link.activation(refresh=True)
        if activation['state'] != 'ready':
            code = {'needs_consent': 'consent_required', 'unavailable': 'provider_unavailable'}.get(
                activation['state'], 'unsafe_configuration')
            return c.response(rid or 'invalid', 'error', error=(code, activation['reason']))
        if not self.link.history_is_cloud_only(request):
            return c.response(rid or 'invalid', 'error', error=(
                'invalid_request', 'El historial no pertenece a esta conversación Cloud. No se envió nada.'))
        return self.link.adapter.converse(request, cancel_event)


class CloudLink:
    def __init__(self, state_dir, config, device_token, transport=None, ca_file=None):
        if not isinstance(config, ClientConfig):
            raise ValueError('Configuración Cloud inválida')
        self.config = config
        self.consent = ConsentStore(Path(state_dir) / 'cloud')
        self.transport = transport or HttpTransport(config.gateway_url, ca_file)
        self.adapter = CloudConversationProvider(config, self.consent, self.transport, device_token)
        self.guard = CloudSessionGuard(self)
        self.chat = Conversations(state_dir, self.guard, 'cloud', source_prefix='cloud')
        self._lock = threading.Lock()
        self._status, self._checked = None, 0.0

    @classmethod
    def from_file(cls, state_dir, config_path, device_token, ca_file=None):
        data = json.loads(Path(config_path).read_text(encoding='utf-8'))
        return cls(state_dir, ClientConfig.from_mapping(data), device_token, ca_file=ca_file)

    def close(self):
        self.chat.close()

    def gateway_status(self, refresh=False):
        with self._lock:
            if refresh or time.monotonic() - self._checked > STATUS_TTL_S:
                self._status, self._checked = self.adapter.gateway_status(), time.monotonic()
            return self._status

    def activation(self, refresh=False):
        disclosure = self.config.disclosure
        gateway = self.gateway_status(refresh)
        if gateway is None:
            return dict(state='unavailable', test=None,
                        reason='No se pudo contactar el gateway Cloud. No se envió nada.')
        test = gateway['provider_mode'] == 'test'
        if gateway['disclosure_digest'] != disclosure.digest():
            return dict(state='blocked', test=test, reason='Las condiciones del gateway no coinciden con las que '
                        'ves acá. No se envía nada hasta actualizar la configuración y volver a aceptar.')
        if not test and not disclosure.terms_verified:
            return dict(state='blocked', test=test, reason='Activación real bloqueada: las condiciones del '
                        'proveedor (retención, límites y precios) todavía no están verificadas.')
        if not self.consent.valid_for(disclosure):
            return dict(state='needs_consent', test=test, reason='Cloud requiere tu consentimiento para estas condiciones.')
        return dict(state='ready', test=test, reason='')

    def status(self, refresh=False):
        d = self.config.disclosure
        info = self.chat.status()
        info.update(
            configured=True, activation=self.activation(refresh), consent_code=d.digest()[:CONFIRM_CHARS],
            disclosure=dict(
                provider=d.provider, model=d.model, region=d.region, data_sent=d.as_dict()['data_sent'],
                gateway_retention_hours=d.gateway_retention_hours, provider_retention_days=d.provider_retention_days,
                terms_verified=d.terms_verified, max_input_chars=d.max_input_chars,
                max_output_tokens=d.max_output_tokens, policy_version=d.policy_version,
                limits_usd=dict(per_user_daily=d.per_user_daily_micro_usd / 1e6,
                                global_daily=d.global_daily_micro_usd / 1e6,
                                global_monthly=d.global_monthly_micro_usd / 1e6)))
        return info

    def accept(self, code):
        activation = self.activation(refresh=True)
        if activation['state'] in ('blocked', 'unavailable'):
            raise ChatError(activation['reason'], 409)
        try:
            self.consent.grant(self.config.disclosure, code)
        except ValueError:
            raise ChatError('El código no coincide con las condiciones mostradas. Recargá y revisalas de nuevo.', 400)
        return self.status(refresh=True)

    def revoke(self):
        self.consent.revoke()
        return self.status(refresh=True)

    def check(self, rid):
        """Explicit 'check status' action: reads the gateway ledger; never resends."""
        self.chat.get(rid)  # only turns of this session
        try:
            found = self.adapter.lookup(rid)
        except Exception:  # noqa: BLE001
            found = None
        if found is None:
            return dict(request_id=rid, state='unknown')
        return found

    def history_is_cloud_only(self, request):
        """Every earlier message must come from a completed turn of this Cloud session."""
        messages = request.get('messages') if isinstance(request, dict) else None
        if not isinstance(messages, list) or not messages:
            return False
        with self.chat.lock:
            done = {}
            for turn in self.chat.turns.values():
                response = turn.get('response') or {}
                if turn['state'] == 'ok' and response.get('status') == 'ok':
                    done.setdefault(turn['request']['messages'][-1]['content'], set()).add(response['reply'])
        history, i = messages[:-1], 0
        while i < len(history):
            user = history[i]
            if user.get('role') != 'user' or user.get('content') not in done:
                return False
            replies = done[user['content']]
            following = history[i + 1] if i + 1 < len(history) else None
            if following is not None and following.get('role') == 'assistant':
                if following.get('content') not in replies:
                    return False
                i += 2
            elif '' in replies:  # a turn that only returned proposals has no assistant text
                i += 1
            else:
                return False
        return True
