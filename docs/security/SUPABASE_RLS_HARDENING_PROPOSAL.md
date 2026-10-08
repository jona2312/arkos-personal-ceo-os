# Propuesta: endurecer permisos de Supabase (no aplicada)

Estado: **propuesta, sin aplicar.** No forma parte de `supabase/migrations/` para que
ninguna herramienta la ejecute por accidente. La evidencia de solo lectura del proyecto
real se entregó fuera de este repositorio porque el repositorio es público.

## Problema (según el esquema de este repo)

- Las migraciones 001–010 crean 9 tablas en `public` sin `ENABLE ROW LEVEL SECURITY`
  (ver `SECURITY_RULES.md` §4: "Pendiente").
- Con los privilegios por defecto de Supabase, `anon` y `authenticated` reciben
  `SELECT/INSERT/UPDATE/DELETE/TRUNCATE` sobre tablas nuevas de `public` y `EXECUTE` sobre
  funciones nuevas.
- Sin RLS, cualquiera con la anon key puede leer o modificar todas las filas por
  PostgREST.
- `search_memory(...)` y `search_items_by_date(...)` son `SECURITY INVOKER`.
  `search_memory` acepta `p_user_id NULL`, que devuelve datos de todos los usuarios.
  Además tienen `search_path` mutable (lint 0011).
- `users.id` es `gen_random_uuid()` y no está ligado a `auth.users`. Las políticas
  `auth.uid() = user_id` de `SECURITY_RULES.md` nunca coincidirían todavía.

## Corrección propuesta

```sql
begin;

-- 1) RLS en todas las tablas. Sin políticas = acceso denegado a anon/authenticated.
--    service_role tiene BYPASSRLS y no se ve afectado.
alter table public.users                   enable row level security;
alter table public.arkos_items             enable row level security;
alter table public.arkos_messages          enable row level security;
alter table public.arkos_daily_summaries   enable row level security;
alter table public.arkos_email_summaries   enable row level security;
alter table public.arkos_meeting_minutes   enable row level security;
alter table public.arkos_expenses          enable row level security;
alter table public.arkos_approvals         enable row level security;
alter table public.arkos_memory_embeddings enable row level security;

-- 2) Defensa en profundidad: sin privilegios directos para roles de cliente.
revoke all on all tables    in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;

-- 3) RPCs solo para el backend.
revoke execute on function public.search_memory(text, uuid, integer)                       from public, anon, authenticated;
revoke execute on function public.search_memory(vector, double precision, integer, uuid)   from public, anon, authenticated;
revoke execute on function public.search_items_by_date(uuid, date)                         from public, anon, authenticated;
grant  execute on function public.search_memory(text, uuid, integer)                       to service_role;
grant  execute on function public.search_memory(vector, double precision, integer, uuid)   to service_role;
grant  execute on function public.search_items_by_date(uuid, date)                         to service_role;

-- 4) search_path fijo (lint 0011).
alter function public.search_memory(text, uuid, integer)                     set search_path = public, pg_temp;
alter function public.search_memory(vector, double precision, integer, uuid) set search_path = public, pg_temp;
alter function public.search_items_by_date(uuid, date)                       set search_path = public, pg_temp;
alter function public.update_updated_at_column()                             set search_path = public, pg_temp;

-- 5) Objetos futuros creados por postgres no quedan expuestos por defecto.
alter default privileges for role postgres in schema public revoke all     on tables    from anon, authenticated;
alter default privileges for role postgres in schema public revoke all     on sequences from anon, authenticated;
alter default privileges for role postgres in schema public revoke execute on functions from anon, authenticated;

commit;
```

Fuera de este cambio:
- **Políticas para `authenticated`:** primero hay que agregar `users.auth_user_id uuid
  references auth.users` y escribir políticas sobre esa columna, cuando exista un
  dashboard con Supabase Auth.
- **Mover la extensión `vector` fuera de `public` (lint 0014):** cambia la resolución
  del tipo `vector` en columnas y funciones; requiere su propia prueba.
- **Privilegios por defecto de `supabase_admin`:** no se pueden alterar con el rol
  `postgres`. Las tablas nuevas creadas desde el dashboard igual quedan cubiertas,
  pero se debe habilitar RLS en cada una.

## Impacto en n8n

| Workflow (en Git) | Llamada | Clave |
|---|---|---|
| ARKOS_WHATSAPP_CLOUD_INBOX | `POST /rest/v1/arkos_messages` (inbound y outbound) | `SUPABASE_SERVICE_ROLE_KEY` |
| ARKOS_WHATSAPP_CLOUD_INBOX_IMPORT | `POST /rest/v1/arkos_messages` | `SUPABASE_SERVICE_ROLE_KEY` |
| ARKOS_MEMORY_WRITE | `POST /rest/v1/arkos_items` | `SUPABASE_SERVICE_ROLE_KEY` |
| ARKOS_MEMORY_SEARCH | `POST /rest/v1/rpc/search_memory` | `SUPABASE_SERVICE_ROLE_KEY` |
| ARKOS_APPROVAL_HANDLER | `POST /rest/v1/arkos_approvals` | `SUPABASE_SERVICE_ROLE_KEY` |

- **Impacto esperado: ninguno** si la instancia desplegada de n8n coincide con Git, porque
  `service_role` ignora RLS y conserva sus privilegios.
- **Riesgo:** la instancia desplegada no se verificó. Si algún nodo o credencial usa la
  anon key, empezará a recibir 401/403 o `42501 permission denied`.
- Tampoco se ven afectados el relay (#2), que no usa Supabase, ni el Task Center (#3),
  que es solo local.

## Procedimiento sugerido (cuando Jona lo decida)

1. Revisar en n8n desplegado (Settings → Variables y credenciales) que ningún nodo use
   `SUPABASE_ANON_KEY`.
2. Aplicar el bloque SQL en una rama de Supabase o en una ventana de mantenimiento, con
   respaldo previo.
3. Verificar con consultas de catálogo:
   - `pg_class.relrowsecurity = true` en las 9 tablas.
   - `information_schema.role_table_grants` sin filas para `anon`/`authenticated`.
   - `has_function_privilege('anon', …) = false` en las 3 RPC.
   - Advisors sin `rls_disabled_in_public`.
4. Correr las pruebas de Fase 1 de n8n: "Hola Arkos", memoria write, memoria search,
   aprobación y número no autorizado.
5. Comprobar con la anon key que `GET /rest/v1/users` devuelve `[]` o 401.

## Reversión

```sql
begin;
grant select, insert, update, delete on all tables in schema public to anon, authenticated;  -- estado previo (no recomendado)
grant usage, select on all sequences in schema public to anon, authenticated;
grant execute on function public.search_memory(text, uuid, integer), public.search_memory(vector, double precision, integer, uuid), public.search_items_by_date(uuid, date) to anon, authenticated;
-- Repetir por tabla: alter table public.<tabla> disable row level security;
commit;
```
