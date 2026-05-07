# ARKOS — Schema Supabase

Documentacion completa del schema de base de datos PostgreSQL en Supabase para ARKOS Personal CEO OS.

---

## Extensiones requeridas

| Extension | Uso |
|-----------|-----|
| pgvector | Embeddings y busqueda semantica (vector cosine similarity) |

---

## Tabla: users

Migration: `001_init_users.sql`

Tabla de usuarios del sistema. En la instancia actual solo existe un usuario (el owner/CEO).

| Columna | Tipo | Default | Constraint |
|---------|------|---------|------------|
| id | uuid | gen_random_uuid() | PRIMARY KEY |
| name | text | — | NOT NULL |
| phone | text | — | UNIQUE |
| email | text | — | — |
| role | text | 'owner' | — |
| timezone | text | 'America/Argentina/Buenos_Aires' | — |
| preferences | jsonb | '{}' | — |
| created_at | timestamptz | now() | — |
| updated_at | timestamptz | now() | Trigger: update_updated_at_column |

**Triggers:**

- `users_updated_at` — BEFORE UPDATE, ejecuta `update_updated_at_column()`.

**Seed data:**

Se inserta el owner (Jona Romero) con ON CONFLICT (phone) DO NOTHING.

---

## Tabla: arkos_items

Migrations: `002_arkos_items.sql` + `010_workflow_compatibility.sql`

Tabla central del sistema. Almacena tareas, notas, recordatorios, ideas, decisiones, seguimientos, y cualquier item que ARKOS deba recordar.

| Columna | Tipo | Default | Constraint |
|---------|------|---------|------------|
| id | uuid | gen_random_uuid() | PRIMARY KEY |
| user_id | uuid | — | NOT NULL, FK -> users(id) ON DELETE CASCADE |
| title | text | — | NOT NULL |
| description | text | — | — |
| content | text | — | Agregado en 010. Los workflows usan este campo en vez de description |
| item_type | text | — | NOT NULL, CHECK in ('task','note','reminder','calendar_event','decision','idea','follow_up','expense','meeting_minute') |
| area | text | 'general' | — |
| project | text | — | — |
| category | text | — | — |
| department | text | — | Agregado en 010. Clasificacion por department (agenda_ops, docs_comms, finance_control) |
| tags | text[] | '{}' | Agregado en 010. Array de tags |
| status | text | 'pending' | CHECK in ('pending','active','done','cancelled','waiting','archived') |
| priority | text | 'medium' | CHECK in ('low','medium','high','urgent') |
| due_date | timestamptz | — | — |
| remind_at | timestamptz | — | — |
| reminded | boolean | false | — |
| assigned_to | text | — | Persona responsable si no es el owner |
| depends_on | uuid | — | Referencia a otro item |
| source | text | 'whatsapp' | CHECK in ('whatsapp','manual','calendar','email','system','dashboard') |
| raw_input | text | — | Input original del usuario |
| transcription | text | — | Transcripcion de audio |
| metadata | jsonb | '{}' | — |
| created_at | timestamptz | now() | — |
| updated_at | timestamptz | now() | Trigger: update_updated_at_column |

**Indices:**

| Nombre | Columnas | Condicion |
|--------|----------|-----------|
| idx_items_user_status | (user_id, status) | — |
| idx_items_user_type | (user_id, item_type) | — |
| idx_items_due_date | (due_date) | WHERE status = 'pending' |
| idx_items_remind_at | (remind_at) | WHERE reminded = false |
| idx_items_area | (area) | — |
| idx_items_project | (project) | WHERE project IS NOT NULL |
| idx_items_department | (department) | WHERE department IS NOT NULL |

**Triggers:**

- `arkos_items_updated_at` — BEFORE UPDATE, ejecuta `update_updated_at_column()`.

**Notas de migracion 010:**

- `content` se agrego porque los workflows usan `content` en vez de `description`. Se migran datos existentes con `UPDATE arkos_items SET content = description WHERE content IS NULL AND description IS NOT NULL`.
- `item_type` se amplio con `expense` y `meeting_minute`.
- `status` se amplio con `active`.

---

## Tabla: arkos_messages

Migration: `003_messages.sql`

Historial completo de conversaciones. Guarda tanto mensajes inbound (del usuario) como outbound (de ARKOS).

| Columna | Tipo | Default | Constraint |
|---------|------|---------|------------|
| id | uuid | gen_random_uuid() | PRIMARY KEY |
| user_id | uuid | — | NOT NULL, FK -> users(id) ON DELETE CASCADE |
| direction | text | — | NOT NULL, CHECK in ('inbound','outbound') |
| channel | text | 'whatsapp' | — |
| message_type | text | — | CHECK in ('text','audio','image','document','system') |
| external_message_id | text | — | ID del mensaje en WhatsApp Cloud API |
| from_phone | text | — | — |
| to_phone | text | — | — |
| text_content | text | — | Contenido del mensaje |
| media_url | text | — | — |
| media_id | text | — | WhatsApp media ID para descargar |
| transcription | text | — | Transcripcion de audio |
| intent | text | — | Intent clasificado por el CEO Agent |
| department | text | — | Department asignado |
| parsed_json | jsonb | '{}' | JSON parseado de la respuesta del agente |
| processed | boolean | false | — |
| processing_error | text | — | Error de procesamiento si hubo |
| created_at | timestamptz | now() | — |

**Indices:**

| Nombre | Columnas | Condicion |
|--------|----------|-----------|
| idx_messages_user_created | (user_id, created_at DESC) | — |
| idx_messages_external_id | (external_message_id) | WHERE external_message_id IS NOT NULL |
| idx_messages_unprocessed | (processed) | WHERE processed = false |

---

## Tabla: arkos_daily_summaries

Migration: `004_daily_summaries.sql`

Resumenes diarios generados por ARKOS. Incluye resumen matutino, vespertino, tareas clave y decisiones del dia.

| Columna | Tipo | Default | Constraint |
|---------|------|---------|------------|
| id | uuid | gen_random_uuid() | PRIMARY KEY |
| user_id | uuid | — | NOT NULL, FK -> users(id) ON DELETE CASCADE |
| summary_date | date | — | NOT NULL |
| morning_summary | text | — | — |
| evening_summary | text | — | — |
| focus_of_day | text | — | — |
| day_score | jsonb | '{}' | — |
| key_tasks | jsonb | '[]' | — |
| pending_items | jsonb | '[]' | — |
| completed_items | jsonb | '[]' | — |
| decisions | jsonb | '[]' | — |
| created_at | timestamptz | now() | — |
| updated_at | timestamptz | now() | Trigger: update_updated_at_column |

**Indices:**

| Nombre | Columnas | Condicion |
|--------|----------|-----------|
| idx_daily_summaries_user_date | (user_id, summary_date) | UNIQUE |

**Triggers:**

- `arkos_daily_summaries_updated_at` — BEFORE UPDATE, ejecuta `update_updated_at_column()`.

---

## Tabla: arkos_email_summaries

Migration: `005_email_summaries.sql` (Fase 6)

Resumenes de emails procesados por ARKOS. Clasifica importancia, sugiere acciones y trackea deadlines.

| Columna | Tipo | Default | Constraint |
|---------|------|---------|------------|
| id | uuid | gen_random_uuid() | PRIMARY KEY |
| user_id | uuid | — | NOT NULL, FK -> users(id) ON DELETE CASCADE |
| email_id | text | — | — |
| thread_id | text | — | — |
| sender | text | — | — |
| recipients | text[] | — | — |
| subject | text | — | — |
| summary | text | — | — |
| importance | text | — | CHECK in ('low','medium','high','critical') |
| area | text | — | — |
| project | text | — | — |
| suggested_action | text | — | — |
| requires_response | boolean | false | — |
| deadline | timestamptz | — | — |
| raw_metadata | jsonb | '{}' | — |
| created_at | timestamptz | now() | — |

**Indices:**

| Nombre | Columnas | Condicion |
|--------|----------|-----------|
| idx_email_summaries_importance | (user_id, importance) | — |
| idx_email_summaries_requires_response | (requires_response) | WHERE requires_response = true |

---

## Tabla: arkos_meeting_minutes

Migration: `006_meeting_minutes.sql` (Fase 6)

Minutas de reuniones con participantes, decisiones, action items y riesgos.

| Columna | Tipo | Default | Constraint |
|---------|------|---------|------------|
| id | uuid | gen_random_uuid() | PRIMARY KEY |
| user_id | uuid | — | NOT NULL, FK -> users(id) ON DELETE CASCADE |
| title | text | — | NOT NULL |
| meeting_date | timestamptz | now() | — |
| participants | text[] | — | — |
| summary | text | — | — |
| decisions | jsonb | '[]' | — |
| action_items | jsonb | '[]' | — |
| risks | jsonb | '[]' | — |
| next_steps | jsonb | '[]' | — |
| source | text | 'whatsapp' | — |
| raw_transcript | text | — | — |
| created_at | timestamptz | now() | — |
| updated_at | timestamptz | now() | Trigger: update_updated_at_column |

**Triggers:**

- `arkos_meeting_minutes_updated_at` — BEFORE UPDATE, ejecuta `update_updated_at_column()`.

---

## Tabla: arkos_expenses

Migration: `007_expenses.sql` (Fase 7)

Gastos, facturas y vencimientos. Soporta scope personal/business y tracking de estado de pago.

| Columna | Tipo | Default | Constraint |
|---------|------|---------|------------|
| id | uuid | gen_random_uuid() | PRIMARY KEY |
| user_id | uuid | — | NOT NULL, FK -> users(id) ON DELETE CASCADE |
| title | text | — | NOT NULL |
| description | text | — | — |
| amount | numeric | — | — |
| currency | text | 'ARS' | — |
| expense_date | date | — | — |
| due_date | date | — | — |
| vendor | text | — | — |
| category | text | — | — |
| subcategory | text | — | — |
| scope | text | — | CHECK in ('personal','business') |
| company | text | — | — |
| project | text | — | — |
| payment_status | text | 'pending' | CHECK in ('pending','paid','cancelled','needs_review') |
| payment_method | text | — | — |
| receipt_url | text | — | — |
| source | text | 'whatsapp' | — |
| raw_input | text | — | — |
| extracted_data | jsonb | '{}' | — |
| created_at | timestamptz | now() | — |
| updated_at | timestamptz | now() | Trigger: update_updated_at_column |

**Indices:**

| Nombre | Columnas | Condicion |
|--------|----------|-----------|
| idx_expenses_user_status | (user_id, payment_status) | — |
| idx_expenses_due_date | (due_date) | WHERE payment_status = 'pending' |
| idx_expenses_scope | (scope) | — |

**Triggers:**

- `arkos_expenses_updated_at` — BEFORE UPDATE, ejecuta `update_updated_at_column()`.

---

## Tabla: arkos_approvals

Migration: `008_approvals.sql`

Log de aprobaciones. Toda accion sensible que ARKOS quiera ejecutar pasa por esta tabla antes de ejecutarse.

| Columna | Tipo | Default | Constraint |
|---------|------|---------|------------|
| id | uuid | gen_random_uuid() | PRIMARY KEY |
| user_id | uuid | — | NOT NULL, FK -> users(id) ON DELETE CASCADE |
| action_type | text | — | NOT NULL |
| action_payload | jsonb | — | NOT NULL |
| action_description | text | — | Descripcion legible para el owner |
| status | text | 'pending' | CHECK in ('pending','approved','rejected','expired','executed') |
| confirmation_message | text | — | — |
| approved_at | timestamptz | — | — |
| rejected_at | timestamptz | — | — |
| executed_at | timestamptz | — | — |
| expires_at | timestamptz | — | Tiempo limite para aprobar |
| created_at | timestamptz | now() | — |

**Indices:**

| Nombre | Columnas | Condicion |
|--------|----------|-----------|
| idx_approvals_pending | (user_id, status) | WHERE status = 'pending' |

---

## Tabla: arkos_memory_embeddings

Migration: `009_memory_embeddings.sql`

Memoria semantica con embeddings vectoriales. Usa pgvector con indice HNSW para busqueda por cosine similarity.

| Columna | Tipo | Default | Constraint |
|---------|------|---------|------------|
| id | uuid | gen_random_uuid() | PRIMARY KEY |
| user_id | uuid | — | NOT NULL, FK -> users(id) ON DELETE CASCADE |
| source_table | text | — | Tabla de origen ('arkos_items', 'arkos_messages', etc.) |
| source_id | uuid | — | ID del registro original |
| content | text | — | NOT NULL. Texto original |
| summary | text | — | Resumen corto para contexto rapido |
| area | text | — | — |
| project | text | — | — |
| memory_type | text | — | 'conversation', 'task', 'decision', 'meeting', 'expense' |
| embedding | vector(1536) | — | OpenAI text-embedding-3-small (1536 dimensiones) |
| metadata | jsonb | '{}' | — |
| created_at | timestamptz | now() | — |

**Indices:**

| Nombre | Tipo | Columnas | Parametros |
|--------|------|----------|------------|
| idx_memory_embedding_hnsw | HNSW | (embedding vector_cosine_ops) | m = 16, ef_construction = 64 |
| idx_memory_user | B-tree | (user_id) | — |

---

## Funciones RPC

### search_memory (version vector — 009)

Busqueda semantica en `arkos_memory_embeddings` usando cosine similarity con pgvector.

```sql
search_memory(
  query_embedding vector(1536),
  match_threshold float DEFAULT 0.7,
  match_count int DEFAULT 5,
  p_user_id uuid DEFAULT NULL
)
```

**Retorna:**

| Columna | Tipo |
|---------|------|
| id | uuid |
| content | text |
| summary | text |
| area | text |
| project | text |
| memory_type | text |
| similarity | float |
| created_at | timestamptz |

**Logica:** Filtra por `1 - (embedding <=> query_embedding) > match_threshold`, ordena por distancia coseno ascendente. Si se pasa `p_user_id`, filtra por usuario.

---

### search_memory (version texto — 010)

Busqueda por texto simple en `arkos_items` + `arkos_messages` usando ILIKE. Version Day 1 que no requiere embeddings.

```sql
search_memory(
  search_text text,
  p_user_id uuid DEFAULT NULL,
  match_count int DEFAULT 5
)
```

**Retorna:**

| Columna | Tipo |
|---------|------|
| id | uuid |
| item_type | text |
| title | text |
| content | text |
| department | text |
| status | text |
| due_date | timestamptz |
| created_at | timestamptz |
| source_table | text |

**Logica:**

1. Busca en `arkos_items` donde title, content o description coincidan con ILIKE `%search_text%`. Excluye items con status `cancelled` o `archived`. Limite: `match_count`.
2. UNION ALL con busqueda en `arkos_messages` donde text_content coincida y direction sea `inbound`. Limite: 3 mensajes.
3. Resultado ordenado por `created_at DESC`, limite total: `match_count`.

**Nota:** PostgreSQL resuelve la sobrecarga por tipo del primer parametro (vector vs text).

---

### search_items_by_date (010)

Busqueda de items por fecha especifica. Util para consultas tipo "que tengo el sabado".

```sql
search_items_by_date(
  p_user_id uuid,
  p_date date
)
```

**Retorna:**

| Columna | Tipo |
|---------|------|
| id | uuid |
| item_type | text |
| title | text |
| content | text |
| department | text |
| status | text |
| due_date | timestamptz |
| remind_at | timestamptz |

**Logica:** Busca en `arkos_items` donde `DATE(due_date) = p_date` o `DATE(remind_at) = p_date`. Excluye items cancelled/archived. Ordena por `due_date ASC`.

---

### update_updated_at_column (001)

Funcion trigger generica que actualiza `updated_at` a `now()` antes de cada UPDATE.

```sql
update_updated_at_column() RETURNS trigger
```

**Usada por triggers en:** users, arkos_items, arkos_daily_summaries, arkos_meeting_minutes, arkos_expenses.

---

## Diagrama de relaciones

```
users (id)
  |-- 1:N --> arkos_items (user_id)
  |-- 1:N --> arkos_messages (user_id)
  |-- 1:N --> arkos_daily_summaries (user_id)
  |-- 1:N --> arkos_email_summaries (user_id)
  |-- 1:N --> arkos_meeting_minutes (user_id)
  |-- 1:N --> arkos_expenses (user_id)
  |-- 1:N --> arkos_approvals (user_id)
  |-- 1:N --> arkos_memory_embeddings (user_id)

arkos_items (depends_on) --> arkos_items (id)  [self-reference]
arkos_memory_embeddings (source_id) --> [tabla indicada en source_table]
```

---

## Orden de ejecucion de migrations

```
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
```

La migracion 010 depende de 002 (modifica arkos_items) y de 003 (referencia arkos_messages en la funcion search_memory). Debe ejecutarse al final.
