# ARKOS Personal CEO OS — Arquitectura v2

## Tesis estrategica: De SaaS a GaaS / Agentic as a Service

ARKOS se disena bajo una tesis estrategica: el software empresarial esta evolucionando desde SaaS hacia modelos agentic, donde el valor no esta solamente en ofrecer una herramienta, sino en entregar trabajo ejecutado por agentes.

En el modelo SaaS tradicional, el usuario entra a una plataforma, carga datos, presiona botones y realiza el trabajo.

En el modelo GaaS / Agentic as a Service, el usuario conversa con un agente, delega objetivos, aprueba decisiones sensibles y recibe resultados.

ARKOS sera el primer sistema interno de INB construido bajo esta logica.

---

## Decision arquitectonica clave (2026-05-06)

ARKOS nace desde el dia 1 como CEO Agent con memoria persistente y tres subagentes internos. El workflow de WhatsApp es solo la puerta de entrada, no el cerebro.

No se construye primero un bot basico para despues "meterle cerebro". La arquitectura correcta va desde el inicio, aunque algunas tools arranquen como mock/simple.

---

## Arquitectura agentic

```text
WhatsApp Cloud API
       |
   n8n Webhook
       |
ARKOS_WHATSAPP_CLOUD_INBOX (canal puro)
  - recibe, valida, parsea, normaliza
  - guarda inbound en Supabase
  - delega al cerebro
       |
ARKOS_CEO_AGENT (cerebro central)
  - consulta memoria (pgvector + items)
  - clasifica intencion
  - decide subagente/department
  - ejecuta tools
  - pide aprobacion si corresponde
  - guarda outbound y memoria nueva
       |
  +----+----+----+
  |         |         |
agenda_ops  docs_comms  finance_control
  |         |         |
  +----+----+---------+
       |
 Tools / Sub-workflows
  - buscar_memoria
  - guardar_memoria
  - enviar_whatsapp_texto
  - enviar_whatsapp_audio
  - pedir_aprobacion
       |
 Respuesta texto/audio a Jona
```

---

## Workflows en n8n

### Canal de entrada

| Workflow | Funcion |
|----------|---------|
| ARKOS_WHATSAPP_CLOUD_INBOX | Recibe WhatsApp, valida, parsea, guarda inbound, delega al CEO Agent, envia respuesta |

### Cerebro

| Workflow | Funcion |
|----------|---------|
| ARKOS_CEO_AGENT | Cerebro central. Consulta memoria, clasifica, decide, ejecuta tools, responde |

### Sub-agentes (futuro, por ahora el CEO Agent maneja los 3 departments)

| Workflow | Department | Estado |
|----------|-----------|--------|
| ARKOS_AGENT_AGENDA_OPS | Tareas, recordatorios, calendario, foco | Dia 4 |
| ARKOS_AGENT_DOCS_COMMS | Mails, minutas, decisiones, borradores | Dia 4 |
| ARKOS_AGENT_FINANCE_CONTROL | Gastos, facturas, vencimientos | Dia 4 |

### Tools (sub-workflows)

| Workflow | Tool | Estado |
|----------|------|--------|
| ARKOS_MEMORY_SEARCH | buscar_memoria | Dia 1 |
| ARKOS_MEMORY_WRITE | guardar_memoria | Dia 1 |
| ARKOS_SEND_WHATSAPP_TEXT | enviar_whatsapp_texto | Dia 1 |
| ARKOS_SEND_WHATSAPP_AUDIO | enviar_whatsapp_audio (TTS Marin) | Dia 3 |
| ARKOS_APPROVAL_HANDLER | pedir_aprobacion | Dia 1 |

### Crons (futuro)

| Workflow | Funcion | Estado |
|----------|---------|--------|
| ARKOS_REMINDER_CRON | Enviar recordatorios pendientes | Dia 2 |
| ARKOS_MORNING_BRIEFING | Resumen matutino proactivo | Dia 2 |

---

## Flujo principal (Dia 1)

```
1. Jona envia mensaje por WhatsApp
2. Meta envia webhook POST a n8n (ARKOS_WHATSAPP_CLOUD_INBOX)
3. n8n valida webhook / numero autorizado
4. Parsea y normaliza input
5. Guarda inbound en arkos_messages
6. Llama a ARKOS_CEO_AGENT via HTTP
7. CEO Agent busca memoria relevante en Supabase/pgvector
8. Enriquece contexto con memoria
9. Envia a OpenAI gpt-4o-mini con system prompt ARKOS CEO
10. Parsea respuesta: intent, department, items, response
11. Si intent != chat: guarda item en arkos_items (memoria)
12. Retorna respuesta al INBOX
13. INBOX envia respuesta por WhatsApp Cloud API
14. Guarda outbound en arkos_messages
15. Responde 200 a Meta
```

---

## Memoria persistente

ARKOS no depende de memoria de sesion. Toda la memoria vive en Supabase.

### Tablas de memoria

| Tabla | Uso |
|-------|-----|
| arkos_items | Tareas, notas, recordatorios, ideas, decisiones, seguimientos |
| arkos_messages | Historial completo de conversaciones |
| arkos_daily_summaries | Resumenes diarios |
| arkos_meeting_minutes | Minutas de reuniones |
| arkos_email_summaries | Resumenes de emails |
| arkos_expenses | Gastos y facturas |
| arkos_memory_embeddings | Embeddings pgvector para busqueda semantica |
| arkos_approvals | Log de aprobaciones pendientes/completadas |

### Busqueda de memoria

El CEO Agent busca memoria ANTES de responder, usando:
1. `search_memory` (funcion Supabase con pgvector) para busqueda semantica
2. Consultas directas a `arkos_items` por tipo, fecha, persona, proyecto

### Escritura de memoria

Despues de cada interaccion relevante, el CEO Agent guarda:
- Tareas creadas
- Notas importantes
- Decisiones tomadas
- Recordatorios con fecha
- Gastos registrados
- Cualquier dato que Jona quiera recordar

---

## Reglas de aprobacion

ARKOS puede hablar proactivamente con Jona.

ARKOS requiere aprobacion explicita para:
- Enviar mails a terceros
- Enviar WhatsApp a terceros
- Mover reuniones sensibles
- Confirmar gastos como pagados
- Borrar informacion
- Compartir documentos
- Llamar a terceros

---

## Variables de entorno requeridas en n8n

| Variable | Descripcion |
|----------|-------------|
| SUPABASE_URL | URL del proyecto Supabase |
| SUPABASE_SERVICE_ROLE_KEY | Service role key de Supabase |
| OWNER_USER_ID | UUID de Jona en tabla users |
| OPENAI_API_KEY | API key de OpenAI |
| WHATSAPP_ACCESS_TOKEN | Token de WhatsApp Cloud API |
| WHATSAPP_PHONE_NUMBER_ID | Phone Number ID de Meta |
| N8N_BASE_URL | URL base de n8n (para llamadas entre workflows) |

---

## ARKOS como capa madre de asistentes

ARKOS Personal CEO OS sera la capa central de coordinacion de Jona y del ecosistema INB.

Cada unidad de negocio podra tener su propio asistente operativo. Esos asistentes reportan a ARKOS. ARKOS filtra, resume, prioriza y escala solo lo importante.

### Jerarquia

```text
Jona / Direccion INB
        |
ARKOS Personal CEO OS
        |
ARKOS CEO Agent
 |-- Agenda & Operaciones
 |-- Documentos & Comunicacion
 |-- Finanzas & Control
        |
Ecosistema de asistentes verticales (futuro)
 |-- INNA / INMEJORA
 |-- Finanzas / INBIG Finanzas
 |-- Campus / INBIG Campus
 |-- INPiensa / Automatizaciones
 |-- Futuros clientes B2B
```

---

## Modelo replicable para INB LAB

La arquitectura de ARKOS es modular y replicable. Solo cambian:
- El system prompt
- La base de conocimiento
- Los permisos
- Las herramientas conectadas
- El dashboard
- La voz
- El contexto del negocio

---

## Componentes tecnicos

| Componente | Tecnologia |
|-----------|-----------|
| Canal entrada | WhatsApp Cloud API |
| Orquestador | n8n |
| Cerebro IA | OpenAI gpt-4o-mini (router) + gpt-4o (vision/complejo) |
| DB operativa | Supabase PostgreSQL |
| Memoria semantica | pgvector + HNSW index |
| TTS | OpenAI gpt-4o-mini-tts, voz Marin, formato opus |
| STT | OpenAI Whisper |
| Vision | OpenAI gpt-4o |
| Calendario | Google Calendar API |
| Email | Gmail API |
| Dashboard | Next.js + Supabase |
| Memoria visible | Obsidian Markdown (espejo) |

---

## Plan de implementacion

| Dia | Objetivo |
|-----|----------|
| 1 | WhatsApp Cloud API + CEO Agent + memoria basica + respuesta texto |
| 2 | Crear tareas/recordatorios reales + buscar memoria + crons |
| 3 | Audio entrante (Whisper) + audio saliente (TTS Marin) |
| 4 | Subagentes separados como sub-workflows |
| 5 | Dashboard basico Next.js |

---

## Seguridad

- Tokens en variables de entorno, nunca hardcodeados
- RLS en Supabase por user_id
- Webhook verificado con token secreto
- Solo numeros autorizados pueden hablar con ARKOS
- Logs de todas las acciones sensibles
- Aprobacion humana para acciones externas
