# ARKOS — Reglas de Seguridad

Documentacion de todas las capas de seguridad implementadas y pendientes en ARKOS Personal CEO OS.

---

## 1. Autenticacion webhook Meta (WhatsApp Cloud API)

Meta envia un GET de verificacion al configurar el webhook y un POST por cada mensaje entrante.

### Verificacion inicial (GET)

- Meta envia `hub.mode`, `hub.verify_token` y `hub.challenge`.
- ARKOS valida que `hub.verify_token` coincida con la variable de entorno `WHATSAPP_VERIFY_TOKEN`.
- Si coincide, responde con `hub.challenge` (status 200).
- Si no coincide, responde 403.

### Mensajes entrantes (POST)

- El payload viene firmado por Meta. En la implementacion actual n8n no valida la firma X-Hub-Signature-256 del payload (pendiente para produccion).
- Se valida el numero del remitente contra `AUTHORIZED_OWNER_PHONE` antes de cualquier procesamiento.

---

## 2. Numero autorizado (AUTHORIZED_OWNER_PHONE)

Solo el numero configurado en `AUTHORIZED_OWNER_PHONE` puede interactuar con ARKOS.

- El workflow ARKOS_WHATSAPP_CLOUD_INBOX valida el numero antes de guardar el mensaje o llamar al CEO Agent.
- Mensajes de numeros no autorizados se descartan silenciosamente (respuesta 200 a Meta para evitar reintentos, sin procesar).
- Numeros no autorizados no consumen tokens de OpenAI ni generan registros en la base de datos.

---

## 3. Secret interno entre workflows (X-Arkos-Secret)

Las llamadas HTTP entre workflows de n8n usan un header de autenticacion interno.

- **Header:** `X-Arkos-Secret`
- **Variable de entorno:** `ARKOS_INTERNAL_SECRET`
- El workflow ARKOS_CEO_AGENT valida este header al recibir requests. Si no coincide, rechaza la solicitud.
- Todos los sub-workflows (MEMORY_SEARCH, MEMORY_WRITE, SEND_WHATSAPP_TEXT, SEND_WHATSAPP_AUDIO, APPROVAL_HANDLER) deben validar este header.
- Esto previene que actores externos llamen directamente a los webhooks internos de n8n.

---

## 4. Row Level Security (RLS) en Supabase

**Estado: Pendiente de implementar.**

Actualmente los workflows usan `service_role_key` que bypasea RLS. Cuando se implemente RLS, las politicas deben ser:

### Politicas requeridas por tabla

**Todas las tablas con user_id:**

```sql
-- Lectura: solo registros del propio usuario
CREATE POLICY "Users can read own data" ON [tabla]
  FOR SELECT USING (auth.uid() = user_id);

-- Insercion: solo puede insertar con su propio user_id
CREATE POLICY "Users can insert own data" ON [tabla]
  FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Actualizacion: solo puede actualizar sus propios registros
CREATE POLICY "Users can update own data" ON [tabla]
  FOR UPDATE USING (auth.uid() = user_id);

-- Eliminacion: solo puede eliminar sus propios registros
CREATE POLICY "Users can delete own data" ON [tabla]
  FOR DELETE USING (auth.uid() = user_id);
```

**Tablas afectadas:**

- arkos_items
- arkos_messages
- arkos_daily_summaries
- arkos_email_summaries
- arkos_meeting_minutes
- arkos_expenses
- arkos_approvals
- arkos_memory_embeddings

**Tabla users:**

```sql
-- Solo puede leer su propio perfil
CREATE POLICY "Users can read own profile" ON users
  FOR SELECT USING (auth.uid() = id);

-- Solo puede actualizar su propio perfil
CREATE POLICY "Users can update own profile" ON users
  FOR UPDATE USING (auth.uid() = id);
```

### Notas de implementacion

- RLS debe habilitarse con `ALTER TABLE [tabla] ENABLE ROW LEVEL SECURITY`.
- Los workflows server-side seguiran usando `service_role_key` (bypasea RLS).
- RLS se activa cuando exista un dashboard con autenticacion por usuario (Next.js + Supabase Auth).
- Las funciones RPC (search_memory, search_items_by_date) ya reciben `p_user_id` como parametro, lo que facilita la transicion.

---

## 5. Variables sensibles

Todas las variables sensibles viven exclusivamente en variables de entorno. Nunca se hardcodean en workflows, codigo fuente ni documentacion publica.

### Variables sensibles

| Variable | Descripcion | Nivel de sensibilidad |
|----------|-------------|----------------------|
| SUPABASE_SERVICE_ROLE_KEY | Acceso total a Supabase (bypasea RLS) | Critico |
| OPENAI_API_KEY | API key de OpenAI | Critico |
| WHATSAPP_ACCESS_TOKEN | Token de WhatsApp Cloud API | Critico |
| ARKOS_INTERNAL_SECRET | Secret entre workflows | Alto |
| WHATSAPP_VERIFY_TOKEN | Token de verificacion webhook Meta | Alto |

### Variables no sensibles (pero privadas)

| Variable | Descripcion |
|----------|-------------|
| SUPABASE_URL | URL del proyecto Supabase |
| OWNER_USER_ID | UUID del owner en tabla users |
| WHATSAPP_PHONE_NUMBER_ID | Phone Number ID de Meta |
| AUTHORIZED_OWNER_PHONE | Numero autorizado (sin +) |
| N8N_BASE_URL | URL base de n8n |

### Reglas

- Nunca commitear archivos `.env` al repositorio.
- El `.gitignore` debe incluir `.env`, `.env.local`, `.env.production`.
- En n8n, usar Environment Variables (Settings > Variables) o credenciales encriptadas.
- Rotar tokens periodicamente (especialmente WHATSAPP_ACCESS_TOKEN que expira).
- El `SUPABASE_SERVICE_ROLE_KEY` nunca debe exponerse al frontend.

---

## 6. Reglas de aprobacion humana

ARKOS opera bajo el principio de que puede actuar autonomamente en acciones internas, pero requiere aprobacion explicita del owner para acciones que afecten a terceros o sean irreversibles.

### Acciones que ARKOS puede ejecutar sin aprobacion

- Crear tareas, notas, recordatorios, ideas, decisiones en arkos_items
- Guardar mensajes en arkos_messages
- Buscar en memoria (items, mensajes, embeddings)
- Generar resumenes diarios
- Clasificar emails por importancia
- Responder al owner por WhatsApp (canal propio)
- Registrar gastos en arkos_expenses (con status pending)
- Generar minutas de reuniones
- Actualizar prioridad o status de items existentes

### Acciones que requieren aprobacion explicita

| Accion | Motivo |
|--------|--------|
| Enviar emails a terceros | Comunicacion externa irreversible |
| Enviar WhatsApp a terceros | Comunicacion externa irreversible |
| Mover o cancelar reuniones sensibles | Impacto en agenda de terceros |
| Marcar gastos como pagados | Implicacion financiera |
| Borrar informacion (items, notas, etc.) | Accion destructiva irreversible |
| Compartir documentos con terceros | Exposicion de informacion |
| Llamar a terceros | Comunicacion externa |
| Ejecutar pagos o transferencias | Accion financiera critica |
| Modificar datos de contacto de terceros | Impacto en datos maestros |
| Agendar reuniones con terceros | Compromete tiempo de terceros |

### Flujo de aprobacion

1. ARKOS detecta que la accion requiere aprobacion.
2. Crea un registro en `arkos_approvals` con status `pending` y `expires_at` (24 horas por defecto).
3. Envia mensaje al owner describiendo la accion y pidiendo confirmacion.
4. El owner responde "si" o "no" por WhatsApp.
5. El CEO Agent detecta `intent=approval_response`, busca la aprobacion pendiente mas reciente.
6. Si aprobada: status pasa a `approved`, se ejecuta la accion, status pasa a `executed`.
7. Si rechazada: status pasa a `rejected`.
8. Si no hay respuesta en 24h: status pasa a `expired`.

---

## 7. Log de acciones sensibles

Todas las acciones sensibles se registran en la tabla `arkos_approvals`, independientemente de si fueron aprobadas, rechazadas o expiraron.

### Campos de auditoria

| Campo | Uso |
|-------|-----|
| action_type | Tipo de accion (send_email, send_whatsapp, delete_item, etc.) |
| action_payload | JSON completo con los parametros de la accion |
| action_description | Texto legible que se mostro al owner |
| status | Estado actual (pending, approved, rejected, expired, executed) |
| approved_at / rejected_at / executed_at | Timestamps de cada transicion |
| created_at | Cuando se creo la solicitud |

### Reglas de logging

- Toda accion que requiere aprobacion genera un registro, sin excepcion.
- Los registros no se borran. Son un audit trail permanente.
- El campo `action_payload` contiene toda la informacion necesaria para reproducir la accion.
- Si la accion falla despues de ser aprobada, se debe registrar el error en `action_payload`.

---

## 8. Uso de service_role_key

La `SUPABASE_SERVICE_ROLE_KEY` tiene acceso total a la base de datos y bypasea RLS.

### Reglas

- Solo se usa en workflows server-side (n8n, API routes del backend).
- Nunca se expone al frontend (dashboard, aplicacion web).
- El dashboard usa `anon_key` + autenticacion de usuario via Supabase Auth.
- Cuando se migre a API propia (Node.js/Next.js), la service_role_key vive solo en el servidor.

---

## 9. Seguridad de red

### Estado actual (n8n)

- Los webhooks de n8n estan expuestos en la URL publica de n8n.
- La validacion de `WHATSAPP_VERIFY_TOKEN` protege contra llamadas aleatorias al webhook de Meta.
- El `X-Arkos-Secret` protege contra llamadas directas a los webhooks internos.

### Mejoras pendientes para produccion

- Validar firma `X-Hub-Signature-256` de Meta en cada POST (verificacion criptografica del payload).
- Rate limiting en webhooks.
- IP whitelisting para los webhooks de Meta (IPs conocidas de Meta).
- HTTPS obligatorio en todos los endpoints.
- Monitoreo de llamadas fallidas y alertas por intentos no autorizados.

---

## Resumen de capas de seguridad

```
Capa 1: Verificacion webhook Meta (verify_token)
Capa 2: Numero autorizado (AUTHORIZED_OWNER_PHONE)
Capa 3: Secret interno (X-Arkos-Secret)
Capa 4: RLS por user_id (pendiente)
Capa 5: Variables en env (nunca hardcodeadas)
Capa 6: Aprobacion humana (acciones externas/destructivas)
Capa 7: Audit trail (arkos_approvals)
Capa 8: service_role_key solo server-side
```
