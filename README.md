# ARKOS Personal CEO OS

> Tu CEO no necesita otro dashboard. Necesita un agente que piense, recuerde y actue.

ARKOS es un sistema operativo ejecutivo basado en agentes con memoria persistente, interfaz por WhatsApp, voz conversacional y aprobacion humana para acciones sensibles.

Construido bajo la tesis de transicion de SaaS a Agentic as a Service (GaaS): el valor no esta en la herramienta, sino en el trabajo ejecutado por el agente.

---

## Arquitectura

```text
WhatsApp Cloud API
       |
   n8n Webhook
       |
ARKOS_WHATSAPP_CLOUD_INBOX (canal puro)
       |
ARKOS_CEO_AGENT (cerebro central)
  |-- search_memory (Supabase)
  |-- write_memory (Supabase)
  |-- send_whatsapp_text
  |-- send_whatsapp_audio (TTS Marin)
  |-- approval_handler
       |
  Tres departments internos:
  1. Agenda & Operaciones
  2. Documentos & Comunicacion
  3. Finanzas & Control
```

---

## Stack

| Componente | Tecnologia |
|-----------|-----------|
| Canal | WhatsApp Business Platform / Cloud API |
| Orquestador | n8n |
| Cerebro IA | OpenAI gpt-4o-mini (router) + gpt-4o (vision/complejo) |
| DB operativa | Supabase PostgreSQL |
| Memoria semantica | pgvector + HNSW index |
| TTS | OpenAI gpt-4o-mini-tts, voz Marin, formato opus |
| STT | OpenAI Whisper |
| Dashboard | Next.js + Supabase (futuro) |
| Memoria visible | Obsidian Markdown (futuro) |

---

## Estructura del repositorio

```
arkos-personal-ceo-os/
  docs/
    ARCHITECTURE.md          # Arquitectura agentic v2
    N8N_WORKFLOWS.md         # Documentacion de los 7 workflows
    SUPABASE_SCHEMA.md       # Schema completo de base de datos
    SECURITY_RULES.md        # Reglas de seguridad y aprobacion
    MIGRATION_TO_ARKOS_CORE_API.md  # Tool contracts para migracion
    WHATSAPP_CLOUD_API_SETUP.md     # Setup WhatsApp Cloud API
    ROADMAP.md               # Roadmap por fases
    CHECKLIST_FASE_1.md      # Checklist operativo Fase 1
    ARKOS_PERSONAL_CEO_OS_MASTER_SPEC.md  # Spec completa
  supabase/
    migrations/
      001_init_users.sql
      002_arkos_items.sql
      003_messages.sql
      004_daily_summaries.sql
      005_email_summaries.sql
      006_meeting_minutes.sql
      007_expenses.sql
      008_approvals.sql
      009_memory_embeddings.sql
      010_workflow_compatibility.sql
  n8n/
    workflows/               # 7 workflows JSON para importar
      ARKOS_WHATSAPP_CLOUD_INBOX.json
      ARKOS_CEO_AGENT.json
      ARKOS_MEMORY_SEARCH.json
      ARKOS_MEMORY_WRITE.json
      ARKOS_SEND_WHATSAPP_TEXT.json
      ARKOS_SEND_WHATSAPP_AUDIO.json
      ARKOS_APPROVAL_HANDLER.json
    notes/
      workflow-test-plan.md  # 10 tests E2E
  prompts/
    arkos_ceo_router.md      # System prompt CEO Agent
    tts_marin_voice.md       # Config voz TTS
  .env.example
  .gitignore
```

---

## Reglas de aprobacion

ARKOS puede actuar autonomamente: guardar notas, crear tareas, recordatorios, resumir mails, generar minutas.

ARKOS requiere aprobacion explicita para:
- Enviar mails a terceros
- Enviar WhatsApp a terceros
- Mover reuniones sensibles
- Confirmar gastos como pagados
- Borrar informacion
- Compartir documentos
- Llamar a terceros

---

## Quickstart

1. Crear proyecto Supabase y ejecutar migrations 001-010
2. Importar workflows en n8n (orden en N8N_WORKFLOWS.md)
3. Configurar variables de entorno (ver .env.example)
4. Activar todos los workflows
5. Configurar webhook Meta con URL n8n + verify token
6. Enviar "Hola Arkos" por WhatsApp

---

## Documentacion

| Documento | Contenido |
|-----------|-----------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Arquitectura agentic, flujo principal, componentes |
| [N8N_WORKFLOWS.md](docs/N8N_WORKFLOWS.md) | 7 workflows documentados con flujo y webhooks |
| [SUPABASE_SCHEMA.md](docs/SUPABASE_SCHEMA.md) | 9 tablas, indices, funciones RPC |
| [SECURITY_RULES.md](docs/SECURITY_RULES.md) | Seguridad, RLS, aprobaciones |
| [MIGRATION_TO_ARKOS_CORE_API.md](docs/MIGRATION_TO_ARKOS_CORE_API.md) | Tool contracts para migracion futura |
| [WHATSAPP_CLOUD_API_SETUP.md](docs/WHATSAPP_CLOUD_API_SETUP.md) | Setup WhatsApp Cloud API en Meta |
| [ROADMAP.md](docs/ROADMAP.md) | Roadmap Fases 0-8 |

---

## Estado actual

Fase 1 en deploy. Schema, workflows y documentacion completos.

---

## Licencia

Proyecto privado. Jona Romero / INB.
