# ARKOS — Migracion de n8n a API Propia

Documentacion del mapeo entre workflows n8n actuales y los endpoints REST futuros cuando ARKOS migre a su propio backend (Node.js / Next.js API routes).

---

## 1. ARKOS_WHATSAPP_CLOUD_INBOX

**Rol actual:** Canal de entrada. Recibe webhooks de Meta, valida, parsea, delega al CEO Agent, envia respuesta.

### Mapeo

| Campo | Valor |
|-------|-------|
| Workflow n8n | ARKOS_WHATSAPP_CLOUD_INBOX |
| Webhook actual | `/webhook/arkos-whatsapp` |
| Futuro endpoint | `POST /webhooks/whatsapp` |
| Segundo endpoint | `GET /webhooks/whatsapp` (verificacion Meta) |

### GET /webhooks/whatsapp (verificacion)

**Request (query params):**

```json
{
  "hub.mode": "subscribe",
  "hub.verify_token": "string",
  "hub.challenge": "string"
}
```

**Response (200):** El valor de `hub.challenge` como texto plano.

**Response (403):** Token invalido.

### POST /webhooks/whatsapp (mensajes)

**Headers requeridos:**

| Header | Valor |
|--------|-------|
| Content-Type | application/json |
| X-Hub-Signature-256 | Firma HMAC del payload (validar en produccion) |

**Request body:**

```json
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "string",
      "changes": [
        {
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {
              "display_phone_number": "string",
              "phone_number_id": "string"
            },
            "messages": [
              {
                "from": "string",
                "id": "string",
                "timestamp": "string",
                "type": "text | audio | image | document",
                "text": { "body": "string" },
                "audio": { "id": "string", "mime_type": "string" },
                "image": { "id": "string", "mime_type": "string" }
              }
            ]
          },
          "field": "messages"
        }
      ]
    }
  ]
}
```

**Response body (200):**

```json
{
  "status": "ok"
}
```

**Notas de migracion:**

- Meta requiere respuesta 200 en menos de 20 segundos. El procesamiento pesado (CEO Agent) debe ser asincrono.
- Validar `X-Hub-Signature-256` con HMAC SHA256 usando el App Secret de Meta.
- Filtrar status updates y payloads sin mensajes antes de procesar.

---

## 2. ARKOS_CEO_AGENT

**Rol actual:** Cerebro central. Recibe contexto del mensaje, busca memoria, clasifica, ejecuta tools, responde.

### Mapeo

| Campo | Valor |
|-------|-------|
| Workflow n8n | ARKOS_CEO_AGENT |
| Webhook actual | `/webhook/arkos-ceo-agent` |
| Futuro endpoint | `POST /api/agent/process` |

### POST /api/agent/process

**Headers requeridos:**

| Header | Valor |
|--------|-------|
| Content-Type | application/json |
| X-Arkos-Secret | Valor de ARKOS_INTERNAL_SECRET |

**Request body:**

```json
{
  "user_id": "uuid",
  "message": {
    "text": "string",
    "type": "text | audio | image | document",
    "media_url": "string | null",
    "transcription": "string | null",
    "from_phone": "string",
    "external_message_id": "string",
    "timestamp": "string"
  },
  "context": {
    "channel": "whatsapp",
    "conversation_history": []
  }
}
```

**Response body (200):**

```json
{
  "response_text": "string",
  "intent": "string",
  "department": "string",
  "requires_approval": false,
  "items_created": [
    {
      "id": "uuid",
      "item_type": "string",
      "title": "string"
    }
  ],
  "approval_id": "uuid | null",
  "metadata": {}
}
```

**Notas de migracion:**

- El system prompt del CEO Agent esta embebido en el workflow. Migrarlo a un archivo de configuracion o base de datos.
- La logica de routing a sub-agentes (agenda_ops, docs_comms, finance_control) debe implementarse como funciones internas, no como HTTP calls.
- Las llamadas a tools (memory_search, memory_write, etc.) pasan a ser llamadas a funciones directas en vez de HTTP a sub-workflows.

---

## 3. ARKOS_MEMORY_SEARCH

**Rol actual:** Tool para buscar en memoria persistente (items + mensajes).

### Mapeo

| Campo | Valor |
|-------|-------|
| Workflow n8n | ARKOS_MEMORY_SEARCH |
| Webhook actual | `/webhook/arkos-memory-search` |
| Futuro endpoint | `POST /api/memory/search` |

### POST /api/memory/search

**Headers requeridos:**

| Header | Valor |
|--------|-------|
| Content-Type | application/json |
| X-Arkos-Secret | Valor de ARKOS_INTERNAL_SECRET |

**Request body:**

```json
{
  "user_id": "uuid",
  "query": "string",
  "search_type": "text | vector",
  "match_count": 5,
  "match_threshold": 0.7,
  "filters": {
    "item_type": "string | null",
    "department": "string | null",
    "date_from": "date | null",
    "date_to": "date | null"
  }
}
```

**Response body (200):**

```json
{
  "results": [
    {
      "id": "uuid",
      "item_type": "string",
      "title": "string",
      "content": "string",
      "department": "string",
      "status": "string",
      "due_date": "timestamptz | null",
      "created_at": "timestamptz",
      "source_table": "string",
      "similarity": "float | null"
    }
  ],
  "search_type_used": "text | vector",
  "total_results": 5
}
```

**Notas de migracion:**

- Actualmente usa la funcion RPC `search_memory` (version texto). Cuando haya embeddings reales, usar la version vector.
- El endpoint debe intentar busqueda vector primero y hacer fallback a texto si no hay embeddings disponibles.
- Agregar soporte para busqueda por fecha via `search_items_by_date`.

---

## 4. ARKOS_MEMORY_WRITE

**Rol actual:** Tool para guardar items en memoria (arkos_items).

### Mapeo

| Campo | Valor |
|-------|-------|
| Workflow n8n | ARKOS_MEMORY_WRITE |
| Webhook actual | `/webhook/arkos-memory-write` |
| Futuro endpoint | `POST /api/memory/write` |

### POST /api/memory/write

**Headers requeridos:**

| Header | Valor |
|--------|-------|
| Content-Type | application/json |
| X-Arkos-Secret | Valor de ARKOS_INTERNAL_SECRET |

**Request body:**

```json
{
  "user_id": "uuid",
  "item_type": "task | note | reminder | calendar_event | decision | idea | follow_up | expense | meeting_minute",
  "title": "string",
  "content": "string | null",
  "department": "string | null",
  "priority": "low | medium | high | urgent",
  "status": "pending | active",
  "due_date": "timestamptz | null",
  "remind_at": "timestamptz | null",
  "tags": ["string"],
  "area": "string",
  "project": "string | null",
  "assigned_to": "string | null",
  "source": "whatsapp | manual | calendar | email | system | dashboard",
  "raw_input": "string | null",
  "metadata": {}
}
```

**Response body (201):**

```json
{
  "id": "uuid",
  "item_type": "string",
  "title": "string",
  "status": "string",
  "created_at": "timestamptz"
}
```

**Notas de migracion:**

- Despues de guardar el item, generar embedding asincrono y guardarlo en `arkos_memory_embeddings`.
- Validar item_type contra los valores permitidos del CHECK constraint.
- Retornar 400 si faltan campos obligatorios (user_id, item_type, title).

---

## 5. ARKOS_SEND_WHATSAPP_TEXT

**Rol actual:** Tool para enviar mensajes de texto por WhatsApp Cloud API.

### Mapeo

| Campo | Valor |
|-------|-------|
| Workflow n8n | ARKOS_SEND_WHATSAPP_TEXT |
| Webhook actual | `/webhook/arkos-send-text` |
| Futuro endpoint | `POST /api/whatsapp/send-text` |

### POST /api/whatsapp/send-text

**Headers requeridos:**

| Header | Valor |
|--------|-------|
| Content-Type | application/json |
| X-Arkos-Secret | Valor de ARKOS_INTERNAL_SECRET |

**Request body:**

```json
{
  "to": "string",
  "text": "string",
  "user_id": "uuid",
  "context": {
    "message_id": "string | null"
  }
}
```

**Response body (200):**

```json
{
  "success": true,
  "whatsapp_message_id": "string",
  "message_db_id": "uuid"
}
```

**Notas de migracion:**

- Llama a `POST https://graph.facebook.com/v21.0/{phone_number_id}/messages` con el token de WhatsApp.
- Guardar el mensaje outbound en arkos_messages despues de enviar.
- Si el destinatario no es el owner (AUTHORIZED_OWNER_PHONE), la accion debe pasar por aprobacion primero.

---

## 6. ARKOS_SEND_WHATSAPP_AUDIO

**Rol actual:** Tool para generar audio TTS y enviar por WhatsApp. Mock en Fase 1.

### Mapeo

| Campo | Valor |
|-------|-------|
| Workflow n8n | ARKOS_SEND_WHATSAPP_AUDIO |
| Webhook actual | `/webhook/arkos-send-audio` |
| Futuro endpoint | `POST /api/whatsapp/send-audio` |

### POST /api/whatsapp/send-audio

**Headers requeridos:**

| Header | Valor |
|--------|-------|
| Content-Type | application/json |
| X-Arkos-Secret | Valor de ARKOS_INTERNAL_SECRET |

**Request body:**

```json
{
  "to": "string",
  "text": "string",
  "user_id": "uuid",
  "voice": "marin",
  "format": "opus",
  "context": {
    "message_id": "string | null"
  }
}
```

**Response body (200):**

```json
{
  "success": true,
  "whatsapp_message_id": "string",
  "message_db_id": "uuid",
  "audio_duration_seconds": 0
}
```

**Notas de migracion:**

- Flujo completo: OpenAI TTS genera audio opus -> POST a Meta Media API para subir -> recibe media_id -> POST /messages con type=audio y media_id.
- Modelo TTS: gpt-4o-mini-tts, voz Marin, formato opus.
- El audio generado no se persiste (se genera y envia). Considerar cache si hay textos repetitivos.

---

## 7. ARKOS_APPROVAL_HANDLER

**Rol actual:** Tool para crear solicitudes de aprobacion en arkos_approvals.

### Mapeo

| Campo | Valor |
|-------|-------|
| Workflow n8n | ARKOS_APPROVAL_HANDLER |
| Webhook actual | `/webhook/arkos-approval` |
| Futuro endpoint | `POST /api/approvals/create` |

### POST /api/approvals/create

**Headers requeridos:**

| Header | Valor |
|--------|-------|
| Content-Type | application/json |
| X-Arkos-Secret | Valor de ARKOS_INTERNAL_SECRET |

**Request body:**

```json
{
  "user_id": "uuid",
  "action_type": "string",
  "action_payload": {},
  "action_description": "string",
  "expires_in_hours": 24
}
```

**Response body (201):**

```json
{
  "id": "uuid",
  "status": "pending",
  "expires_at": "timestamptz",
  "created_at": "timestamptz"
}
```

**Endpoints adicionales futuros:**

| Method | Path | Descripcion |
|--------|------|-------------|
| GET | /api/approvals/pending | Listar aprobaciones pendientes |
| POST | /api/approvals/:id/approve | Aprobar una solicitud |
| POST | /api/approvals/:id/reject | Rechazar una solicitud |
| POST | /api/approvals/:id/execute | Ejecutar una accion aprobada |

**Notas de migracion:**

- El `expires_at` se calcula como `now() + expires_in_hours`.
- Implementar un cron que marque como `expired` las aprobaciones vencidas.
- El flujo de respuesta (cuando el owner responde si/no) actualmente lo maneja el CEO Agent detectando `intent=approval_response`. En la API propia, esto puede ser un endpoint dedicado o seguir siendo parte del procesamiento del agente.

---

## Estrategia de migracion

### Fase actual: n8n como orquestador (Day 1)

n8n es el orquestador inicial de ARKOS. Todos los workflows corren en n8n con webhooks HTTP. Esta decision es correcta para:

- Velocidad de prototipado (visual, sin deploy, edicion en caliente).
- Iteracion rapida sobre flujos y prompts.
- Cero infraestructura adicional (n8n ya esta corriendo).

### Fase futura: API propia (Node.js / Next.js)

Migrar cuando se cumplan una o mas de estas condiciones:

- **Complejidad:** Los workflows de n8n se vuelven dificiles de mantener (mas de 20 nodos, logica condicional compleja).
- **Performance:** La latencia entre sub-workflows via HTTP es un cuello de botella.
- **Escalabilidad:** Se necesitan multiples instancias o procesamiento concurrente.
- **Testing:** Se necesitan tests automatizados y CI/CD.
- **Dashboard:** El frontend Next.js necesita API routes propias y no tiene sentido tener dos backends.

### Principios de migracion

1. **Mantener los mismos contratos.** Los request/response schemas documentados en este archivo son el contrato. La migracion cambia la implementacion, no la interfaz.

2. **Migrar de adentro hacia afuera.** Primero migrar los sub-workflows (tools) a funciones internas. Despues migrar el CEO Agent. Al final migrar el canal de entrada (WhatsApp webhook).

3. **Coexistencia temporal.** Durante la migracion, n8n y la API propia pueden coexistir. Un workflow de n8n puede llamar a un endpoint de la API propia y viceversa, siempre que respeten el contrato.

4. **Un endpoint a la vez.** No migrar todo de golpe. Migrar un endpoint, testearlo en produccion, y recien entonces migrar el siguiente.

### Orden recomendado de migracion

| Orden | Componente | Motivo |
|-------|-----------|--------|
| 1 | ARKOS_MEMORY_SEARCH | Logica simple (query a Supabase). Facil de testear. |
| 2 | ARKOS_MEMORY_WRITE | Logica simple (insert en Supabase + generar embedding). |
| 3 | ARKOS_APPROVAL_HANDLER | Logica simple (insert en Supabase). |
| 4 | ARKOS_SEND_WHATSAPP_TEXT | Logica simple (call a Meta API + insert). |
| 5 | ARKOS_SEND_WHATSAPP_AUDIO | Logica moderada (TTS + upload media + send). |
| 6 | ARKOS_CEO_AGENT | Logica compleja. Migrar cuando los tools ya sean funciones internas. |
| 7 | ARKOS_WHATSAPP_CLOUD_INBOX | Canal de entrada. Migrar al final porque requiere reconfigurar el webhook en Meta. |

### Stack recomendado

| Componente | Tecnologia |
|-----------|-----------|
| Runtime | Node.js 20+ |
| Framework | Next.js App Router (API routes) |
| Base de datos | Supabase (PostgreSQL + pgvector) |
| ORM/Query builder | Supabase JS Client (@supabase/supabase-js) |
| IA | OpenAI SDK (@openai/openai) |
| Validacion | Zod (schemas de request/response) |
| Deploy | Vercel (Next.js) o Railway (Node.js) |
| Crons | Vercel Cron Jobs o pg_cron en Supabase |
