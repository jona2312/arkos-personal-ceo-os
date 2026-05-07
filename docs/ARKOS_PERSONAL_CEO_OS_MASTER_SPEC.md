# ARKOS Personal CEO OS — Master Build Spec

## 1. Contexto general

Estamos construyendo **ARKOS Personal CEO OS**, un asistente ejecutivo personal para Jona Romero, fundador de INB / INbig, pensado primero para uso personal y luego como base replicable para productos B2B, CRMs, asistentes ejecutivos para empresas y sistemas operativos conversacionales.

El objetivo no es crear un chatbot comun. El objetivo es crear un **asistente ejecutivo conversacional con memoria persistente**, capaz de recibir mensajes por WhatsApp, audios, fotos, documentos, mails y eventos de calendario, procesarlos, clasificarlos, guardarlos, recordarlos, resumirlos y actuar bajo reglas de aprobacion.

ARKOS debe funcionar como un unico interlocutor visible para Jona, pero internamente debe delegar tareas a departamentos especializados.

---

## 2. Principio principal del sistema

Jona no debe hablar con varios bots.

Jona habla solamente con:

> **ARKOS CEO**

ARKOS CEO recibe todo, interpreta, consulta memoria, delega internamente, ejecuta flujos y responde.

Internamente existen tres departamentos:

1. **Agenda & Operaciones**
2. **Documentos & Comunicacion**
3. **Finanzas & Control**

Para MVP solo trabajamos con estos tres. Mas adelante pueden agregarse Legal, Ventas, Marketing, Tecnologia o CRM.

---

## 3. Arquitectura general

```text
Jona
  |
WhatsApp personal de Jona
  |
Numero oficial ARKOS en WhatsApp Business Platform / Cloud API
  |
Webhook
  |
n8n / Backend Orquestador
  |
ARKOS CEO Router
  |-- Agenda & Operaciones
  |-- Documentos & Comunicacion
  |-- Finanzas & Control
  |
Supabase + pgvector
  |
Google Calendar / Gmail / Drive
  |
Obsidian Mirror en Markdown
  |
Dashboard Web Simple
  |
OpenAI gpt-4o-mini-tts voz Marin
  |
Respuesta por WhatsApp texto/audio
```

---

## 4. Decisiones tecnicas cerradas

### Canal principal

| Entorno | Solucion |
|---------|----------|
| Produccion | WhatsApp Business Platform / Cloud API |
| Laboratorio | Evolution API (solo pruebas, NO produccion) |

### Orquestacion

**n8n** se usa para:
- Recibir webhooks
- Orquestar flujos
- Conectar WhatsApp Cloud API
- Conectar OpenAI
- Conectar Supabase
- Ejecutar crons
- Conectar Gmail
- Conectar Google Calendar
- Enviar recordatorios
- Generar resumenes

### Memoria

| Capa | Funcion |
|------|---------|
| Supabase | Memoria operativa estructurada |
| pgvector | Memoria semantica (embeddings) |
| Obsidian | Espejo visible en Markdown |
| Google Calendar | Eventos reales |
| Gmail/Drive | Contexto externo |

La memoria NO depende de sesiones temporales. ARKOS recuerda entre dias, semanas y meses.

### Voz

| Campo | Valor |
|-------|-------|
| Provider | OpenAI |
| Model | gpt-4o-mini-tts |
| Voice | marin |
| Format | opus |
| Speed | 1.0 |
| Costo aprox | ~USD 1.50 / 100 min audio output |

---

## 5. Reglas de seguridad

### ARKOS puede hacer libremente:
- Guardar notas
- Crear tareas
- Crear recordatorios
- Mandar mensajes a Jona
- Mandar audios a Jona
- Leer agenda autorizada
- Resumir mails autorizados
- Crear borradores
- Hacer minutas
- Clasificar gastos
- Guardar comprobantes

### ARKOS requiere aprobacion explicita de Jona para:
- Enviar mails
- Enviar WhatsApp a terceros
- Mover reuniones sensibles
- Confirmar gastos como pagados
- Responder clientes
- Compartir documentos
- Llamar a terceros
- Borrar informacion
- Archivar informacion sensible

### ARKOS no debe:
- Hacer pagos
- Firmar documentos
- Enviar mensajes sensibles sin aprobacion
- Dar asesoramiento financiero personalizado
- Tomar decisiones legales o contables definitivas
- Actuar como representante humano sin aclaracion

---

## 6. Objetivo del MVP

Construir una primera version funcional que permita:

1. Jona escribe por WhatsApp a ARKOS
2. ARKOS recibe el mensaje por WhatsApp Cloud API
3. n8n procesa el webhook
4. ARKOS detecta intencion
5. ARKOS guarda la informacion en Supabase
6. ARKOS puede crear tareas, notas, recordatorios y eventos
7. ARKOS puede responder por texto
8. ARKOS puede responder por audio usando OpenAI TTS voz Marin
9. ARKOS puede enviar resumen diario
10. ARKOS puede consultar memoria previa
11. ARKOS puede mostrar informacion en dashboard simple

---

## 7. Alcance del MVP

### Incluido en MVP
- WhatsApp Cloud API
- Webhook n8n
- Recepcion de texto
- Recepcion de audio
- Transcripcion de audio
- Clasificacion de intencion
- Supabase
- Tareas, Notas, Recordatorios
- Follow-ups
- Decisiones pendientes
- Foco diario
- Resumen diario
- Audio saliente con voz Marin
- Dashboard simple
- Google Calendar basico
- Obsidian mirror basico

### No incluido en MVP
- Llamadas telefonicas
- Llamadas a terceros
- Multiempresa
- CRM completo
- Dialogflow CX
- Voice realtime streaming
- Automatizacion de pagos
- Envio autonomo a terceros
- Agentes comerciales
- App movil nativa

---

## 8. Departamentos internos

### 8.1 ARKOS CEO Router

Responsabilidades:
- Recibir todos los mensajes
- Detectar intencion
- Consultar memoria
- Decidir a que departamento derivar
- Pedir confirmacion si la accion es sensible
- Responder a Jona
- Mantener tono ejecutivo, cercano y claro

Tipos de intencion:
```
task, note, reminder, calendar_event, email_summary,
meeting_minute, expense, decision, follow_up, query, chat, approval_request
```

### 8.2 Agenda & Operaciones

Responsabilidades:
- Tareas
- Recordatorios
- Google Calendar
- Foco diario
- Resumen matutino
- Cierre nocturno
- Revision semanal
- Pendientes vencidos
- Pendientes por persona

### 8.3 Documentos & Comunicacion

Responsabilidades:
- Gmail
- Resumen de mails
- Borradores
- Minutas
- Decisiones tomadas
- Documentos
- Seguimientos por persona
- Drive
- Obsidian mirror

### 8.4 Finanzas & Control

Responsabilidades:
- Fotos de facturas
- Tickets
- Comprobantes
- Gastos personales
- Gastos empresa
- Clasificacion por proyecto
- Vencimientos
- Estado de pagos
- Dashboard financiero simple

---

## 9. Modelo de datos Supabase

### 9.1 users

```sql
create table users (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  phone text unique,
  email text,
  role text default 'owner',
  timezone text default 'America/Argentina/Buenos_Aires',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
```

### 9.2 arkos_items

Tabla central para tareas, notas, recordatorios, ideas, decisiones y follow-ups.

```sql
create table arkos_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  title text not null,
  description text,
  item_type text not null check (
    item_type in ('task','note','reminder','calendar_event','decision','idea','follow_up')
  ),
  area text default 'general',
  project text,
  category text,
  status text default 'pending' check (
    status in ('pending','done','cancelled','waiting','archived')
  ),
  priority text default 'medium' check (
    priority in ('low','medium','high','urgent')
  ),
  due_date timestamptz,
  remind_at timestamptz,
  reminded boolean default false,
  source text default 'whatsapp' check (
    source in ('whatsapp','manual','calendar','email','system','dashboard')
  ),
  raw_input text,
  transcription text,
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
```

### 9.3 arkos_messages

```sql
create table arkos_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  direction text check (direction in ('inbound', 'outbound')),
  channel text default 'whatsapp',
  message_type text check (message_type in ('text','audio','image','document','system')),
  external_message_id text,
  from_phone text,
  to_phone text,
  text_content text,
  media_url text,
  transcription text,
  intent text,
  parsed_json jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);
```

### 9.4 arkos_daily_summaries

```sql
create table arkos_daily_summaries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  summary_date date not null,
  morning_summary text,
  evening_summary text,
  focus_of_day text,
  day_score jsonb default '{}'::jsonb,
  key_tasks jsonb default '[]'::jsonb,
  pending_items jsonb default '[]'::jsonb,
  completed_items jsonb default '[]'::jsonb,
  decisions jsonb default '[]'::jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
```

### 9.5 arkos_email_summaries

```sql
create table arkos_email_summaries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  email_id text,
  thread_id text,
  sender text,
  recipients text[],
  subject text,
  summary text,
  importance text check (importance in ('low','medium','high','critical')),
  area text,
  project text,
  suggested_action text,
  requires_response boolean default false,
  deadline timestamptz,
  raw_metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);
```

### 9.6 arkos_meeting_minutes

```sql
create table arkos_meeting_minutes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  title text not null,
  meeting_date timestamptz default now(),
  participants text[],
  summary text,
  decisions jsonb default '[]'::jsonb,
  action_items jsonb default '[]'::jsonb,
  risks jsonb default '[]'::jsonb,
  next_steps jsonb default '[]'::jsonb,
  source text default 'whatsapp',
  raw_transcript text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
```

### 9.7 arkos_expenses

```sql
create table arkos_expenses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  title text not null,
  description text,
  amount numeric,
  currency text default 'ARS',
  expense_date date,
  due_date date,
  vendor text,
  category text,
  subcategory text,
  scope text check (scope in ('personal','business')),
  company text,
  project text,
  payment_status text default 'pending' check (
    payment_status in ('pending','paid','cancelled','needs_review')
  ),
  payment_method text,
  receipt_url text,
  source text default 'whatsapp',
  raw_input text,
  extracted_data jsonb default '{}'::jsonb,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
```

### 9.8 arkos_approvals

```sql
create table arkos_approvals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  action_type text not null,
  action_payload jsonb not null,
  status text default 'pending' check (
    status in ('pending','approved','rejected','expired','executed')
  ),
  confirmation_message text,
  approved_at timestamptz,
  executed_at timestamptz,
  created_at timestamptz default now()
);
```

### 9.9 arkos_memory_embeddings

```sql
create extension if not exists vector;

create table arkos_memory_embeddings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  source_table text,
  source_id uuid,
  content text not null,
  summary text,
  area text,
  project text,
  memory_type text,
  embedding vector(1536),
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz default now()
);
```

---

## 10. Workflows n8n requeridos

### 10.1 ARKOS_WHATSAPP_CLOUD_INBOX

```text
Webhook Trigger
  -> Verificacion de webhook Meta
  -> Parsear mensaje entrante
  -> Guardar mensaje en arkos_messages
  -> Detectar tipo: text/audio/image/document
  -> Si audio: descargar media + transcribir
  -> Si imagen: descargar media + vision si aplica
  -> Enviar texto/transcripcion a ARKOS CEO Router
  -> Recibir JSON estructurado
  -> Ejecutar accion segun intencion
  -> Guardar resultado en Supabase
  -> Responder por WhatsApp texto o audio
```

### 10.2 ARKOS_INTENT_ROUTER (subworkflow)

Responsabilidad:
- Recibir input normalizado
- Consultar memoria relevante
- Clasificar intencion
- Devolver JSON estricto

### 10.3 ARKOS_REMINDER_CRON

Cada 5 minutos:
```text
Cron -> Buscar arkos_items donde remind_at <= now() and reminded = false
     -> Enviar WhatsApp a Jona
     -> Opcional: generar audio si prioridad alta
     -> Actualizar reminded = true
```

### 10.4 ARKOS_MORNING_BRIEFING

Todos los dias 08:00:
```text
Cron -> Google Calendar eventos de hoy
     -> Supabase tareas de hoy
     -> Supabase pendientes vencidos
     -> Supabase decisiones pendientes
     -> LLM genera resumen ejecutivo
     -> TTS Marin genera audio
     -> WhatsApp envia texto + audio
     -> Guardar en arkos_daily_summaries
```

### 10.5 ARKOS_EVENING_REVIEW

Todos los dias 21:30:
```text
Cron -> Consultar tareas completadas
     -> Consultar pendientes
     -> Consultar eventos de manana
     -> Generar cierre del dia
     -> Enviar WhatsApp
     -> Guardar evening_summary
```

### 10.6 ARKOS_WEEKLY_REVIEW

Domingo 19:00:
```text
Cron -> Resumen de semana
     -> Tareas completadas / vencidas
     -> Ideas capturadas
     -> Decisiones tomadas
     -> Foco recomendado proxima semana
     -> Enviar WhatsApp
```

### 10.7 ARKOS_EMAIL_SUMMARY

```text
Gmail Trigger / Cron
  -> Buscar mails nuevos/importantes
  -> Clasificar por prioridad/proyecto
  -> Resumir
  -> Guardar en arkos_email_summaries
  -> Extraer tareas si aplica
  -> Enviar alerta solo si high/critical
```

### 10.8 ARKOS_MEETING_MINUTES

```text
Input: audio/transcript/texto
  -> Transcripcion si aplica
  -> LLM genera minuta
  -> Extraer decisiones
  -> Extraer action items
  -> Guardar en arkos_meeting_minutes
  -> Crear tareas relacionadas
  -> Responder resumen a Jona
```

### 10.9 ARKOS_EXPENSE_VISION

```text
Input: imagen/foto/documento
  -> Descargar media
  -> Modelo vision extrae datos
  -> Detectar monto/proveedor/vencimiento/categoria
  -> Si falta scope personal/business, preguntar a Jona
  -> Guardar en arkos_expenses
  -> Crear recordatorio de vencimiento si aplica
```

### 10.10 ARKOS_OBSIDIAN_SYNC

```text
Cron diario o evento
  -> Leer Supabase
  -> Generar Markdown
  -> Guardar en carpeta Obsidian / repositorio Git
```

Estructura Obsidian:
```
/obsidian-vault
  /Daily
  /Projects
  /People
  /Meetings
  /Decisions
  /Expenses
  /Weekly
```

---

## 11. Prompt principal de ARKOS CEO Router

```
Sos ARKOS CEO, asistente personal y ejecutivo de Jona Romero.

Jona es desarrollador tecnologico e inversor, fundador de INB / INbig, creador de INMEJORA, INBIG Finanzas, INBIG Campus e INPiensa. Tu trabajo es actuar como segundo cerebro operativo y asistente ejecutivo personal.

Tu funcion:
- recibir mensajes de WhatsApp, audios transcritos, imagenes, documentos, mails o eventos;
- interpretar intencion;
- consultar memoria si hace falta;
- clasificar por area;
- separar tareas, notas, recordatorios, decisiones, ideas, gastos, minutas o follow-ups;
- pedir aprobacion para acciones sensibles;
- responder de forma breve, clara, humana y ejecutiva.

No respondas como bot generico. Responde como un asistente de confianza que trabaja con Jona todos los dias.

Areas posibles:
personal, familia, salud, inmejora, inbig_finanzas, inbig_campus, inpiensa, inb_saas,
legal, contable, obra, ventas, marketing, reuniones, finanzas, casa, general

Departamentos internos:
agenda_ops, docs_comms, finance_control, ceo

Reglas:
1. Si el mensaje contiene varias acciones, separalas en varios items.
2. Si hay fecha u hora, normalizala.
3. Si falta hora para una tarea con fecha, usar 09:00 como horario tentativo.
4. Si es una idea estrategica, guardarla como idea, no como tarea.
5. Si depende de otra persona, marcar como follow_up o waiting.
6. Si es evento real, clasificar como calendar_event.
7. Si es gasto o factura, derivar a finance_control.
8. Si es mail/minuta/documento, derivar a docs_comms.
9. Si es tarea/calendario/recordatorio, derivar a agenda_ops.
10. Para enviar mensajes, mails, mover reuniones sensibles, confirmar pagos o llamar a terceros, requires_approval debe ser true.
11. Responder siempre en JSON valido.
12. No inventar datos. Si falta informacion, pedirla.

Formato de salida:
{
  "intent": "create_items|query|update_item|approval_request|chat",
  "department": "agenda_ops|docs_comms|finance_control|ceo",
  "items": [
    {
      "item_type": "task|note|reminder|calendar_event|decision|idea|follow_up|expense|meeting_minute",
      "title": "",
      "description": "",
      "area": "",
      "project": "",
      "category": "",
      "priority": "low|medium|high|urgent",
      "status": "pending|waiting",
      "due_date": "",
      "remind_at": "",
      "metadata": {}
    }
  ],
  "query": {
    "type": "",
    "date_range": "",
    "area": "",
    "status": ""
  },
  "requires_approval": false,
  "approval_reason": "",
  "response_mode": "text|audio|both",
  "confirmation_message": ""
}
```

---

## 12. Prompt para voz TTS Marin

```
Habla en espanol con tono calmo, cercano y ejecutivo.
Sona natural, claro y seguro.
Evita sonar robotico, exagerado o demasiado entusiasta.
Responde como un asistente personal de confianza que acompana a Jona en su dia a dia.
Mantene el mensaje breve, util y accionable.
```

Configuracion:
```json
{
  "provider": "openai",
  "model": "gpt-4o-mini-tts",
  "voice": "marin",
  "format": "opus",
  "speed": 1.0
}
```

---

## 13. Dashboard MVP

Crear dashboard simple en Next.js + Supabase.

Vistas:

1. **Hoy** — Foco del dia, eventos, tareas urgentes, recordatorios, decisiones pendientes, score del dia
2. **Tareas** — Pendientes, vencidas, por proyecto, por prioridad, por estado
3. **Agenda** — Google Calendar, eventos ARKOS, recordatorios
4. **Gastos** — Casa, empresa, INB SAS, INMEJORA, herramientas IA, servicios, vencimientos
5. **Minutas** — Reuniones, decisiones, action items, proximos pasos
6. **Mails** — Mails importantes, requieren respuesta, borradores pendientes
7. **Bandeja inteligente** — Audios, fotos, notas, documentos, pendientes de clasificacion, pendientes de aprobacion

---

## 14. Estructura de repositorio

```
arkos-personal-ceo-os/
  README.md
  .env.example

  /docs
    ARKOS_PERSONAL_CEO_OS_MASTER_SPEC.md
    ARCHITECTURE.md
    ROADMAP.md
    SECURITY_RULES.md
    WHATSAPP_CLOUD_API_SETUP.md
    N8N_WORKFLOWS.md
    SUPABASE_SCHEMA.md
    OBSIDIAN_MEMORY_SPEC.md

  /supabase
    /migrations
      001_init_users.sql
      002_arkos_items.sql
      003_messages.sql
      004_email_summaries.sql
      005_meeting_minutes.sql
      006_expenses.sql
      007_approvals.sql
      008_memory_embeddings.sql
    /policies
    /functions

  /n8n
    /workflows
      ARKOS_WHATSAPP_CLOUD_INBOX.json
      ARKOS_REMINDER_CRON.json
      ARKOS_MORNING_BRIEFING.json
      ARKOS_EVENING_REVIEW.json
      ARKOS_EMAIL_SUMMARY.json
      ARKOS_MEETING_MINUTES.json
      ARKOS_EXPENSE_VISION.json
      ARKOS_OBSIDIAN_SYNC.json
    /notes
      workflow-test-plan.md

  /dashboard
    /app
    /components
    /lib
    /types

  /prompts
    arkos_ceo_router.md
    tts_marin_voice.md
    email_summary.md
    meeting_minutes.md
    expense_vision.md
    daily_briefing.md

  /obsidian
    /templates
      daily-note.md
      project-note.md
      meeting-note.md
      decision-note.md
      expense-note.md
```

---

## 15. Variables de entorno

```env
# Supabase
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ANON_KEY=

# OpenAI
OPENAI_API_KEY=

# WhatsApp Cloud API
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_BUSINESS_ACCOUNT_ID=
WHATSAPP_VERIFY_TOKEN=

# Google
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=

# Security
ARKOS_INTERNAL_SECRET=
WEBHOOK_SECRET=

# Obsidian / Git Sync
OBSIDIAN_VAULT_PATH=
GIT_REPO_PATH=
```

---

## 16. Fases de implementacion

### Fase 0 — Setup
- Crear repo Git
- Crear docs
- Crear proyecto Supabase
- Crear app Meta Developers
- Activar WhatsApp Cloud API con numero de prueba
- Crear credenciales OpenAI
- Crear n8n workflows base

### Fase 1 — MVP conversacion basica
Objetivo: `Jona escribe por WhatsApp -> ARKOS responde por WhatsApp`
- Webhook WhatsApp Cloud API
- Parsear texto
- Guardar mensaje en Supabase
- Enviar respuesta simple
- Primer prompt de ARKOS Router

### Fase 2 — Audio
Objetivo: `Jona manda audio -> ARKOS transcribe -> responde audio con Marin`
- Descargar media desde WhatsApp Cloud API
- Transcribir audio
- Guardar transcripcion
- Generar respuesta
- Convertir a audio con gpt-4o-mini-tts Marin
- Enviar audio por WhatsApp

### Fase 3 — Tareas, notas y recordatorios
Objetivo: `ARKOS captura, guarda y recuerda`
- Crear arkos_items
- Crear recordatorios
- Cron cada 5 minutos
- Consultas tipo "que tengo hoy"
- Foco del dia
- Decisiones pendientes

### Fase 4 — Dashboard simple
Objetivo: `Jona puede ver todo desde una cabina simple`
- Next.js app
- Supabase client
- Vistas: Hoy, Tareas, Agenda, Gastos, Minutas, Bandeja

### Fase 5 — Google Calendar
Objetivo: `ARKOS lee y crea eventos`
- OAuth Google Calendar
- Leer eventos
- Crear eventos
- Recordatorios previos
- Confirmaciones antes de mover reuniones sensibles

### Fase 6 — Gmail y minutas
Objetivo: `ARKOS resume mails y reuniones`
- Gmail API
- Leer mails importantes
- Resumir hilos
- Crear borradores
- Minutas desde audio/texto
- Extraer action items

### Fase 7 — Finanzas & Control
Objetivo: `ARKOS clasifica gastos desde fotos`
- Recibir imagenes
- Extraer datos con vision
- Guardar gastos
- Crear vencimientos
- Dashboard gastos

### Fase 8 — Obsidian Mirror
Objetivo: `ARKOS genera memoria visible en Markdown`
- Templates Markdown
- Daily notes
- Project notes
- Meeting notes
- Decisions
- Git sync opcional

---

## 17. Criterios de exito del MVP

El MVP se considera exitoso si:

1. Jona puede escribirle a ARKOS por WhatsApp
2. ARKOS responde correctamente
3. Jona puede mandar audio
4. ARKOS transcribe el audio
5. ARKOS guarda tareas/notas/recordatorios
6. ARKOS recuerda una tarea futura
7. ARKOS manda audio con voz Marin
8. ARKOS envia resumen diario
9. El dashboard muestra informacion basica
10. La memoria persiste entre sesiones

### Test de validacion:

```
Dia martes:
"Arkos, recordame que el sabado tengo el cumpleanos de mi amigo."

Dia viernes:
"Arkos, te acordas lo del cumpleanos?"

Respuesta esperada:
"Si, Jona. Manana sabado tenes el cumpleanos de tu amigo. Lo tengo registrado. Queres que te lo recuerde unas horas antes?"
```

---

## 18. Criterios de seguridad

Antes de produccion:
- Ningun token hardcodeado
- RLS activo en Supabase
- Webhook validado
- Logs de acciones sensibles
- Aprobaciones guardadas
- Gmail/Calendar con permisos minimos
- No enviar mensajes a terceros sin aprobacion
- No confirmar gastos como pagados sin aprobacion
- No exponer datos personales en logs publicos
- No usar Evolution API en produccion

---

## 19. Frase rectora del proyecto

> ARKOS no es un chatbot. Es un sistema operativo personal y ejecutivo con memoria persistente, WhatsApp como interfaz, voz conversacional, dashboard de control y reglas de aprobacion humana.
