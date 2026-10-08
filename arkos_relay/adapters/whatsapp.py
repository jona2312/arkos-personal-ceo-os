"""WhatsApp Cloud API adapter over the same contract and queue.

Not deployed. Outbound replies are written to channel_outbox; a sender (existing
n8n ARKOS_SEND_WHATSAPP_TEXT or a Cloud API client) still has to drain it.

Commands (Spanish, case-insensitive):
  nota <texto>                 -> note.create awaiting approval
  aprobar <id corto> <huella8> -> approves exactly the content shown (hash prefix)
  cancelar <id corto>
  estado                       -> last tasks
"""
import hashlib
import hmac
import re

from .. import contract as c
from ..store import RelayError

CHANNEL = "whatsapp"
SHORT = 8  # chars of task id / digest shown to the user


def short_id(task):
    return task["id"][4:4 + SHORT]


class WhatsAppAdapter:
    def __init__(self, store, app_secret, verify_token, approval_ttl_seconds=12 * 3600):
        if not app_secret or not verify_token:
            raise ValueError("WhatsApp requiere app secret y verify token")
        self.store = store
        self.app_secret = app_secret.encode()
        self.verify_token = verify_token
        self.approval_ttl_seconds = approval_ttl_seconds

    def verify_subscription(self, query):
        if query.get("hub.mode") == "subscribe" and hmac.compare_digest(query.get("hub.verify_token", ""), self.verify_token):
            return query.get("hub.challenge", "")
        return None

    def valid_signature(self, raw, header):
        expected = "sha256=" + hmac.new(self.app_secret, raw, hashlib.sha256).hexdigest()
        return bool(header) and hmac.compare_digest(expected, header)

    def handle(self, payload):
        handled = 0
        for message in _messages(payload):
            sender, message_id = message.get("from"), message.get("id")
            if not isinstance(sender, str) or not isinstance(message_id, str):
                continue
            user_id = self.store.user_for_channel(CHANNEL, sender)
            if not user_id:
                continue  # unknown numbers are dropped silently, no queue writes
            if not self.store.first_seen(CHANNEL, message_id, user_id):
                continue  # Meta retry of a message already processed
            text = (message.get("text") or {}).get("body", "") if message.get("type") == "text" else ""
            reply = self._command(user_id, message_id, text.strip())
            self.store.enqueue_reply(CHANNEL, sender, user_id, reply)
            handled += 1
        return handled

    def _command(self, user_id, message_id, text):
        lowered = text.lower()
        try:
            if lowered.startswith("nota"):
                body = text[4:].lstrip(" :").strip()
                task, _ = self.store.create_task(user_id, f"wa:{message_id}", "note.create", {"text": body}, channel=CHANNEL)
                return (f"Nota {short_id(task)} pendiente de aprobación:\n«{body[:300]}»\n"
                        f"Para aprobar respondé: aprobar {short_id(task)} {task['payload_sha256'][:SHORT]}")
            match = re.fullmatch(r"aprobar\s+([0-9a-f]{%d})\s+([0-9a-f]{%d})" % (SHORT, SHORT), lowered)
            if match:
                task = self.store.find_by_prefix(user_id, match.group(1))
                if not task["payload_sha256"].startswith(match.group(2)):
                    return "La huella no coincide con esa tarea. No se aprobó nada."
                self.store.approve(user_id, task["id"], task["payload_sha256"], self.approval_ttl_seconds, channel=CHANNEL)
                return f"Aprobada {short_id(task)}. Se ejecutará cuando la PC se conecte."
            match = re.fullmatch(r"cancelar\s+([0-9a-f]{%d})" % SHORT, lowered)
            if match:
                task = self.store.cancel(user_id, self.store.find_by_prefix(user_id, match.group(1))["id"])
                return f"Cancelada {short_id(task)}."
            if lowered == "estado":
                tasks = self.store.list_tasks(user_id, 0, 500)[-5:]
                return "\n".join(f"{short_id(t)} {t['action']} → {t['state']}" for t in tasks) or "Sin tareas."
        except (RelayError, c.ContractError) as exc:
            return f"No se pudo: {getattr(exc, 'message', str(exc))}"
        return "Comandos: «nota <texto>», «aprobar <id> <huella>», «cancelar <id>», «estado»."


def _messages(payload):
    if not isinstance(payload, dict):
        return
    for entry in payload.get("entry") or []:
        for change in (entry or {}).get("changes") or []:
            for message in ((change or {}).get("value") or {}).get("messages") or []:
                if isinstance(message, dict):
                    yield message
