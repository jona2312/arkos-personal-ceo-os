# ARKOS — Documentacion de Workflows n8n

## Arquitectura

```
WhatsApp Cloud API
  -> ARKOS_WHATSAPP_CLOUD_INBOX (canal)
    -> ARKOS_CEO_AGENT (cerebro)
      -> ARKOS_MEMORY_SEARCH (buscar memoria)
      -> ARKOS_MEMORY_WRITE (guardar memoria)
      -> ARKOS_APPROVAL_HANDLER (aprobaciones)
    -> ARKOS_SEND_WHATSAPP_TEXT (respuesta texto)
    -> ARKOS_SEND_WHATSAPP_AUDIO (respuesta audio, Fase 3)
```

---

## Workflows

### 1. ARKOS_WHATSAPP_CLOUD_INBOX

**Rol:** Canal de entrada. Sin logica de negocio.

**Flujo:**
1. Recibe webhook POST/GET de Meta
2. Si GET: valida verify token, responde challenge o 403
3. Si POST: parsea payload WhatsApp Cloud API
4. Valida numero autorizado (env AUTHORIZED_OWNER_PHONE)
5. Filtra status updates y payloads vacios
6. Guarda mensaje inbound en arkos_messages
7. Llama a ARKOS_CEO_AGENT via HTTP (con X-Arkos-Secret)
8. Prepara respuesta (con fallback si CEO Agent falla)
9. Envia respuesta texto por WhatsApp Cloud API
10. Guarda mensaje outbound en arkos_messages
11. Responde 200 a Meta

**Webhook:** `/webhook/arkos-whatsapp`

---

### 2. ARKOS_CEO_AGENT

**Rol:** Cerebro central. Toda la inteligencia vive aqui.

**Flujo:**
1. Valida secret interno (X-Arkos-Secret)
2. Prepara contexto del mensaje
3. Busca memoria relevante en Supabase (search_memory RPC)
4. Enriquece prompt con contexto de memoria
5. Envia a OpenAI gpt-4o-mini con system prompt ARKOS CEO
6. Parsea respuesta: intent, department, items, response
7. Si requires_approval: crea solicitud en arkos_approvals
8. Si intent != chat: guarda items en arkos_items
9. Retorna respuesta formateada

**Webhook:** `/webhook/arkos-ceo-agent`

**System prompt:** Embebido en el workflow. Define tono, reglas, departments, formato JSON.

---

### 3. ARKOS_MEMORY_SEARCH

**Rol:** Tool para buscar en memoria persistente.

**Busca en:** arkos_items + arkos_messages via funcion search_memory de Supabase.

**Webhook:** `/webhook/arkos-memory-search`

---

### 4. ARKOS_MEMORY_WRITE

**Rol:** Tool para guardar items en memoria.

**Guarda en:** arkos_items con tipo, titulo, contenido, department, prioridad, fechas.

**Tipos soportados:** task, note, reminder, calendar_event, decision, idea, follow_up, expense, meeting_minute

**Webhook:** `/webhook/arkos-memory-write`

---

### 5. ARKOS_SEND_WHATSAPP_TEXT

**Rol:** Tool para enviar mensajes de texto por WhatsApp Cloud API.

**Webhook:** `/webhook/arkos-send-text`

---

### 6. ARKOS_SEND_WHATSAPP_AUDIO

**Rol:** Tool para generar audio TTS y enviar por WhatsApp.

**Estado:** Mock en Fase 1. Genera audio con gpt-4o-mini-tts voz Marin pero no sube a WhatsApp Media aun.

**Flujo real (Fase 3):**
```
OpenAI TTS genera opus
  -> POST /{phone_number_id}/media a Meta
  -> Recibe media_id
  -> POST /messages type=audio con media_id
```

**Webhook:** `/webhook/arkos-send-audio`

---

### 7. ARKOS_APPROVAL_HANDLER

**Rol:** Tool para crear solicitudes de aprobacion.

**Guarda en:** arkos_approvals con status=pending, expires_at=24h.

**Flujo de respuesta (pendiente):** Cuando Jona responde "si/no" a una aprobacion, el CEO Agent debe detectar intent=approval_response, buscar la aprobacion pendiente y ejecutar o rechazar.

**Webhook:** `/webhook/arkos-approval`

---

## Variables de entorno

| Variable | Descripcion | Requerida |
|----------|-------------|-----------|
| SUPABASE_URL | URL del proyecto Supabase | Si |
| SUPABASE_SERVICE_ROLE_KEY | Service role key | Si |
| OWNER_USER_ID | UUID de Jona en tabla users | Si |
| OPENAI_API_KEY | API key OpenAI | Si |
| WHATSAPP_ACCESS_TOKEN | Token WhatsApp Cloud API | Si |
| WHATSAPP_PHONE_NUMBER_ID | Phone Number ID de Meta | Si |
| WHATSAPP_VERIFY_TOKEN | Token para verificar webhook | Si |
| AUTHORIZED_OWNER_PHONE | Numero autorizado (sin +) | Si |
| N8N_BASE_URL | URL base de n8n | Si |
| ARKOS_INTERNAL_SECRET | Secret para llamadas entre workflows | Si |

---

## Orden de importacion en n8n

1. ARKOS_MEMORY_SEARCH
2. ARKOS_MEMORY_WRITE
3. ARKOS_SEND_WHATSAPP_TEXT
4. ARKOS_SEND_WHATSAPP_AUDIO
5. ARKOS_APPROVAL_HANDLER
6. ARKOS_CEO_AGENT
7. ARKOS_WHATSAPP_CLOUD_INBOX

---

## Error handling

Todos los nodos HTTP tienen `onError: continueRegularOutput`. Si un servicio falla:
- Save Inbound falla: el flujo sigue, no se pierde el mensaje
- CEO Agent falla: Prepare Response usa fallback "Perdon Jona..."
- Save Outbound falla: la respuesta ya se envio a Jona
- OpenAI falla: Parse CEO Response usa respuesta de error generica

---

## Seguridad

- Verify token validado en webhook Meta
- Numero autorizado validado antes de procesar
- Secret interno (X-Arkos-Secret) entre INBOX y CEO Agent
- Tokens en variables de entorno, nunca hardcodeados
- Numeros no autorizados no consumen tokens OpenAI
