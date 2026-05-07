# ARKOS Personal CEO OS — Roadmap

## Fase 0 — Setup [COMPLETA]

| Tarea | Estado |
|-------|--------|
| Crear repo Git | Done |
| Crear docs base | Done |
| Crear SQL migrations | Done |
| Crear workflow n8n base | Done |
| Crear prompts | Done |
| Auditoria de seguridad (secrets, input mapping, tools) | Done |
| Hardening: env vars en todos los workflows | Done |
| Correccion URLs tools a N8N_BASE_URL | Done |
| Crear app Meta Developers | Pendiente (Jona) |
| Activar WhatsApp Cloud API test | Pendiente (Jona) |
| Crear proyecto Supabase | Pendiente (Jona) |
| Ejecutar migrations en Supabase | Pendiente |
| Configurar n8n con credenciales | Pendiente |

---

## Fase 1 — MVP Conversacion Basica [ACTUAL — en deploy]

**Objetivo:** Jona escribe por WhatsApp -> ARKOS responde con memoria y aprobacion

**Tools activas en Fase 1:** search_memory, write_memory, request_approval

**Tools NO activas en Fase 1:** send_whatsapp_text, send_whatsapp_audio (INBOX responde)

| # | Tarea | Dependencia | Estado |
|---|-------|------------|--------|
| 1 | Rotar ARKOS_INTERNAL_SECRET y WHATSAPP_VERIFY_TOKEN | Auditoria OK | Pendiente |
| 2 | Cargar 10 variables de entorno en n8n | Secrets rotados | Pendiente |
| 3 | Crear credencial OpenAI en n8n | API key activa | Pendiente |
| 4 | Importar 7 workflows en n8n (orden documentado) | Variables cargadas | Pendiente |
| 5 | Asignar credencial OpenAI al CEO Agent | Workflows importados | Pendiente |
| 6 | Activar todos los workflows | Credenciales OK | Pendiente |
| 7 | Crear app Meta Developers | Cuenta Meta | Pendiente (Jona) |
| 8 | Configurar webhook Meta con URL n8n | App creada + workflows activos | Pendiente |
| 9 | Test: verificacion webhook GET | Webhook configurado | Pendiente |
| 10 | Test: "Hola Arkos" por WhatsApp | Webhook verificado | Pendiente |
| 11 | Test: memoria write ("anota que...") | Test 10 OK | Pendiente |
| 12 | Test: memoria search ("que tengo pendiente") | Test 11 OK | Pendiente |
| 13 | Test: aprobacion ("manda mail a X") | Test 12 OK | Pendiente |
| 14 | Test: numero no autorizado | Test 10 OK | Pendiente |
| 15 | Completar checklist Fase 1 | Todos los tests OK | Pendiente |

---

## Fase 1.5 — Subagentes Internos

**Objetivo:** Delegar logica especializada a 3 subagentes sin cambiar la interfaz de Jona

**Regla:** Jona solo habla con ARKOS CEO. Los subagentes son internos e invisibles.

**Criterio de activacion (todos deben cumplirse antes de construir):**

| Criterio | Descripcion |
|----------|-------------|
| Test "Hola Arkos" | Flujo completo funciona |
| Test memoria write | write_memory guarda en Supabase |
| Test memoria search | search_memory retorna resultados |
| Test aprobacion | request_approval crea registro |
| Test numero no autorizado | Mensaje descartado sin procesar |
| Estabilidad | 24-48 hs de uso sin fallos criticos |

**Subagentes a crear:**

| Workflow | Department | Responsabilidades |
|----------|-----------|-------------------|
| ARKOS_AGENT_AGENDA_OPS | Agenda & Operaciones | Tareas, recordatorios, calendario, foco diario, pendientes por persona, resumen diario/semanal |
| ARKOS_AGENT_DOCS_COMMS | Documentos & Comunicacion | Mails, minutas, borradores, documentos, decisiones, seguimiento de conversaciones |
| ARKOS_AGENT_FINANCE_CONTROL | Finanzas & Control | Gastos, facturas, tickets, comprobantes, vencimientos, clasificacion casa/empresa/proyecto |

**Arquitectura de delegacion:**

```
Jona -> WhatsApp -> INBOX -> CEO Agent
                                |
                    clasifica department
                                |
              +--------+--------+--------+
              |                 |                 |
        AGENDA_OPS      DOCS_COMMS    FINANCE_CONTROL
              |                 |                 |
              +--------+--------+--------+
                                |
                    CEO Agent consolida
                                |
                    INBOX -> WhatsApp -> Jona
```

---

## Fase 2 — Audio

**Objetivo:** Audio entrante -> transcripcion -> respuesta con voz Marin

| Tarea | Dependencia |
|-------|------------|
| Descargar media desde WhatsApp Cloud API | Fase 1 completa |
| Transcribir audio con Whisper | Media descargado |
| Guardar transcripcion en arkos_messages | Transcripcion OK |
| Enviar transcripcion al CEO Agent | Flujo existente |
| Generar audio con gpt-4o-mini-tts Marin | Respuesta del Agent |
| Subir audio a WhatsApp Media | Audio generado |
| Enviar mensaje tipo audio | Media subido |

---

## Fase 3 — Tareas, Notas y Recordatorios

**Objetivo:** ARKOS captura, guarda y recuerda

| Tarea | Dependencia |
|-------|------------|
| Crear items en arkos_items desde Router | Fase 1 |
| Workflow ARKOS_REMINDER_CRON | Items con remind_at |
| Consultas: "que tengo hoy" | Items creados |
| Foco del dia | Items + prioridades |
| Resumen matutino (MORNING_BRIEFING) | Cron + items |
| Cierre nocturno (EVENING_REVIEW) | Cron + items |

---

## Fase 4 — Dashboard Simple

**Objetivo:** Cabina visual para Jona

| Tarea | Dependencia |
|-------|------------|
| Setup Next.js + Supabase client | Supabase operativo |
| Vista Hoy | Items + summaries |
| Vista Tareas | arkos_items |
| Vista Agenda | Items tipo calendar_event |
| Vista Gastos | arkos_expenses |
| Vista Minutas | arkos_meeting_minutes |
| Vista Bandeja | arkos_messages sin procesar |
| Deploy | Todo funcional |

---

## Fase 5 — Google Calendar

**Objetivo:** ARKOS lee y crea eventos

| Tarea | Dependencia |
|-------|------------|
| OAuth Google Calendar | Credenciales Google |
| Leer eventos del dia | OAuth OK |
| Crear eventos desde ARKOS | Router + aprobacion |
| Recordatorios pre-evento | Cron + Calendar |
| Incluir en Morning Briefing | Calendar + Briefing |

---

## Fase 6 — Gmail y Minutas

**Objetivo:** ARKOS resume mails y reuniones

| Tarea | Dependencia |
|-------|------------|
| OAuth Gmail | Credenciales Google |
| Leer mails importantes | OAuth OK |
| Resumir hilos | OpenAI + Gmail |
| Crear borradores | Gmail API |
| Minutas desde audio/texto | Transcripcion + LLM |
| Extraer action items de minutas | Minuta generada |

---

## Fase 7 — Finanzas & Control

**Objetivo:** ARKOS clasifica gastos desde fotos

| Tarea | Dependencia |
|-------|------------|
| Recibir imagenes por WhatsApp | Fase 2 (media) |
| Extraer datos con GPT-4o vision | Imagen descargada |
| Guardar en arkos_expenses | Datos extraidos |
| Preguntar scope si falta | Router interactivo |
| Crear vencimientos automaticos | Expense con due_date |
| Dashboard gastos | Fase 4 + expenses |

---

## Fase 8 — Obsidian Mirror

**Objetivo:** Memoria visible en Markdown

| Tarea | Dependencia |
|-------|------------|
| Templates Markdown | Definidos |
| Daily notes automaticas | Summaries |
| Project notes | Items por proyecto |
| Meeting notes | Minutas |
| Decision log | Items tipo decision |
| Git sync opcional | Repo separado |

---

## Future Phase — INB LAB Agentic Platform

**No construir ahora. Solo preparar arquitectura.**

| Asistente | Unidad | Estado |
|-----------|--------|--------|
| INNA | INMEJORA | Futuro |
| Finanzas Assistant | INBIG Finanzas | Futuro |
| Campus Assistant | INBIG Campus | Futuro |
| INPiensa Assistant | INPiensa / SaaS | Futuro |
| B2B Assistants | Clientes | Futuro |

Cada asistente vertical usara el mismo patron de ARKOS pero con:
- Prompt especializado
- Base de conocimiento propia
- Permisos especificos
- Dashboard adaptado
- Reporte a ARKOS o capa INB LAB
