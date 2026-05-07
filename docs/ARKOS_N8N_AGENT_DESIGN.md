# ARKOS N8N Agent Design

Arquitectura de workflows n8n para ARKOS Personal CEO OS.

---

## 1. Por que modular y no un solo workflow

ARKOS no es un workflow monolitico. Cada pieza es un workflow independiente que se comunica via webhooks internos. Las razones:

### Debugging aislado

Si falla la generacion de audio, solo revisas `ARKOS_SEND_WHATSAPP_AUDIO`. No tenes que navegar un workflow de 40 nodos buscando donde se rompio.

### Reutilizacion

Las tools (memoria, envio de mensajes, aprobaciones) pueden ser consumidas por otros sistemas: INMEJORA, INBIG Finanzas, Campus. Cualquier sistema que hable HTTP puede llamar a una tool.

### Escalabilidad independiente

Cada sub-workflow escala por separado. Si la busqueda de memoria es lenta, optimizas solo ese workflow sin tocar el agente.

### Migracion limpia

Cada tool tiene un contrato claro:

```
POST webhook → JSON body → JSON response
```

Para migrar a una API REST propia, solo cambias la URL del webhook. El AI Agent no se entera.

### Limites practicos de n8n

Workflows con muchos nodos se vuelven lentos en el editor visual. Modularizar mantiene cada workflow manejable (5-15 nodos).

---

## 2. Arquitectura de workflows

```
ARKOS_WHATSAPP_CLOUD_INBOX (canal)
         |
         v
ARKOS_CEO_AGENT (cerebro - AI Agent nativo n8n)
         |
         v
   Tools separadas (webhooks internos):
         |
         +-- ARKOS_MEMORY_SEARCH
         +-- ARKOS_MEMORY_WRITE
         +-- ARKOS_SEND_WHATSAPP_TEXT
         +-- ARKOS_SEND_WHATSAPP_AUDIO
         +-- ARKOS_APPROVAL_HANDLER
```

**Flujo principal:**

1. WhatsApp Cloud API envia webhook a `INBOX`
2. `INBOX` valida, guarda en Supabase, llama a `CEO_AGENT`
3. `CEO_AGENT` procesa con AI Agent y decide que tools usar
4. Las tools ejecutan acciones (buscar memoria, enviar mensaje, etc.)
5. `CEO_AGENT` devuelve respuesta final a `INBOX`
6. `INBOX` envia la respuesta por WhatsApp

---

## 3. Que hace cada workflow

### ARKOS_WHATSAPP_CLOUD_INBOX

Canal puro. No tiene logica de negocio.

| Paso | Descripcion |
|------|-------------|
| 1 | Recibe webhook de WhatsApp Cloud API |
| 2 | GET: responde verify token para validacion inicial |
| 3 | POST: extrae mensaje (texto o audio) |
| 4 | Valida que el numero este autorizado |
| 5 | Guarda mensaje inbound en `arkos_messages` (Supabase) |
| 6 | Llama al `CEO_AGENT` via webhook |
| 7 | Recibe respuesta y la envia por WhatsApp |

### ARKOS_CEO_AGENT

Cerebro del sistema. Usa el nodo AI Agent nativo de n8n.

- Recibe contexto del mensaje entrante
- Procesa con el modelo (gpt-4o-mini)
- Decide que tools llamar segun la intencion
- Devuelve respuesta estructurada

### ARKOS_MEMORY_SEARCH

Busca informacion relevante en la memoria de ARKOS.

```
Input:  { "query": "texto a buscar" }
Output: { "results": [...], "count": N }
```

- Genera embedding del query con OpenAI
- Busca en `arkos_memory_embeddings` usando pgvector
- Usa cosine similarity para ranking
- Devuelve los top-K resultados mas relevantes

### ARKOS_MEMORY_WRITE

Guarda contenido nuevo en la memoria.

```
Input:  { "content": "texto", "category": "decision", "source": "whatsapp" }
Output: { "success": true, "item_id": "uuid" }
```

- Crea registro en `arkos_items`
- Genera embedding con OpenAI
- Guarda embedding en `arkos_memory_embeddings`
- Disponible para busqueda semantica futura

### ARKOS_SEND_WHATSAPP_TEXT

Envia mensaje de texto simple.

```
Input:  { "to": "5491112345678", "message": "texto" }
Output: { "success": true, "message_id": "wamid.xxx" }
```

- Llama a WhatsApp Cloud API endpoint `/messages`
- Tipo: text

### ARKOS_SEND_WHATSAPP_AUDIO

Genera y envia nota de voz.

```
Input:  { "to": "5491112345678", "text": "texto a convertir" }
Output: { "success": true, "message_id": "wamid.xxx" }
```

- Genera audio con OpenAI TTS (voz: `onyx`, formato: `opus`)
- Sube el audio a WhatsApp como media
- Envia como mensaje de audio

### ARKOS_APPROVAL_HANDLER

Gestiona flujo de aprobaciones.

```
Input:  { "action": "crear_evento", "details": {...}, "requester": "agent" }
Output: { "approval_id": "uuid", "status": "pending" }
```

- Crea registro de aprobacion pendiente en Supabase
- Notifica a Jona con detalles de la accion
- Espera respuesta (aprobado/rechazado)
- Ejecuta o cancela la accion segun respuesta

---

## 4. Como ARKOS_CEO_AGENT usa el AI Agent

El workflow `CEO_AGENT` usa el **nodo AI Agent nativo de n8n**, no un HTTP Request directo a OpenAI.

### Configuracion del nodo

```
Nodo: AI Agent
├── Model: OpenAI Chat Model
│   └── gpt-4o-mini
├── Memory: Window Buffer Memory (ultimos mensajes)
├── System Prompt: personalidad ARKOS + reglas + areas
└── Tools:
    ├── HTTP Request Tool → ARKOS_MEMORY_SEARCH
    ├── HTTP Request Tool → ARKOS_MEMORY_WRITE
    ├── HTTP Request Tool → ARKOS_SEND_WHATSAPP_TEXT
    ├── HTTP Request Tool → ARKOS_SEND_WHATSAPP_AUDIO
    └── HTTP Request Tool → ARKOS_APPROVAL_HANDLER
```

### Tools como HTTP Request

Cada tool esta configurada como un nodo **HTTP Request Tool** dentro del AI Agent. Cuando el modelo decide usar una tool:

1. n8n ejecuta el HTTP Request correspondiente
2. Envia POST al webhook interno de la tool
3. Incluye header `x-arkos-secret` para autenticacion
4. Recibe respuesta JSON
5. El modelo interpreta el resultado y continua

### System prompt

El system prompt define:

- Personalidad de ARKOS (asistente ejecutivo, directo, proactivo)
- Reglas de comportamiento (cuando pedir aprobacion, cuando actuar)
- Areas de gestion (agenda, finanzas, equipos, proyectos)
- Instrucciones de uso de cada tool

---

## 5. Seguridad: x-arkos-secret

Todos los webhooks internos estan protegidos con un header de autenticacion.

### Mecanismo

```
Header: x-arkos-secret: <valor-secreto>
```

### Validacion en cada tool

```
IF header.x-arkos-secret != ENV.ARKOS_SECRET
  RETURN 403 Forbidden
```

### Reglas

| Regla | Detalle |
|-------|---------|
| Scope | Todos los webhooks internos (tools) |
| Quien lo conoce | Solo `ARKOS_CEO_AGENT` |
| Sin header | 403 Forbidden |
| Header incorrecto | 403 Forbidden |
| INBOX | Valida ademas numero de telefono autorizado |

### Capas de seguridad

1. **x-arkos-secret**: protege tools de acceso no autorizado
2. **Numero autorizado**: solo Jona puede hablar con ARKOS via WhatsApp
3. **Verify token**: WhatsApp Cloud API valida el webhook del INBOX
4. **Supabase RLS**: datos protegidos a nivel de base de datos

---

## 6. Path de migracion a backend propio

Cada tool tiene un contrato claro que facilita la migracion futura.

### Contrato actual

```
POST https://n8n.arkos.app/webhook/arkos-memory-search
Headers: { "x-arkos-secret": "xxx" }
Body: { "query": "texto" }
Response: { "results": [...] }
```

### Contrato futuro (API propia)

```
POST https://api.arkos.app/v1/memory/search
Headers: { "Authorization": "Bearer xxx" }
Body: { "query": "texto" }
Response: { "results": [...] }
```

### Pasos de migracion

1. Crear endpoint equivalente en API propia (NestJS/FastAPI)
2. Validar que el contrato de entrada/salida sea identico
3. Cambiar la URL en el HTTP Request Tool del AI Agent
4. Desactivar el workflow n8n correspondiente
5. Repetir para cada tool

### Que NO cambia

- El nodo AI Agent sigue igual
- El system prompt sigue igual
- Las definiciones de tools siguen iguales
- Solo cambian las URLs

Documentacion detallada del plan de migracion: [`MIGRATION_TO_ARKOS_CORE_API.md`](./MIGRATION_TO_ARKOS_CORE_API.md)

---

## Referencias

- [ARCHITECTURE.md](./ARCHITECTURE.md) — Arquitectura general del sistema
- [N8N_WORKFLOWS.md](./N8N_WORKFLOWS.md) — Detalle tecnico de cada workflow
- [SECURITY_RULES.md](./SECURITY_RULES.md) — Reglas de seguridad completas
- [MIGRATION_TO_ARKOS_CORE_API.md](./MIGRATION_TO_ARKOS_CORE_API.md) — Plan de migracion
