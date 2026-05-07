# ARKOS Personal CEO OS — Roadmap

## Fase 0 — Setup [ACTUAL]

| Tarea | Estado |
|-------|--------|
| Crear repo Git | Done |
| Crear docs base | Done |
| Crear SQL migrations | Done |
| Crear workflow n8n base | Done |
| Crear prompts | Done |
| Crear app Meta Developers | Pendiente (Jona) |
| Activar WhatsApp Cloud API test | Pendiente (Jona) |
| Crear proyecto Supabase | Pendiente (Jona) |
| Ejecutar migrations en Supabase | Pendiente |
| Configurar n8n con credenciales | Pendiente |

---

## Fase 1 — MVP Conversacion Basica

**Objetivo:** Jona escribe por WhatsApp -> ARKOS responde

| Tarea | Dependencia |
|-------|------------|
| Configurar webhook en Meta | App creada |
| Importar workflow en n8n | n8n operativo |
| Conectar credenciales Supabase | Proyecto creado |
| Conectar credenciales OpenAI | API key activa |
| Test: verificacion webhook | Webhook configurado |
| Test: recepcion mensaje | Webhook verificado |
| Test: guardado en Supabase | Credenciales OK |
| Test: clasificacion Router | OpenAI conectado |
| Test: respuesta WhatsApp | Todo conectado |
| Completar checklist Fase 1 | Todos los tests |

---

## Fase 2 — Audio

**Objetivo:** Audio entrante -> transcripcion -> respuesta con voz Marin

| Tarea | Dependencia |
|-------|------------|
| Descargar media desde WhatsApp Cloud API | Fase 1 completa |
| Transcribir audio con Whisper | Media descargado |
| Guardar transcripcion en arkos_messages | Transcripcion OK |
| Enviar transcripcion al Router | Flujo existente |
| Generar audio con gpt-4o-mini-tts Marin | Respuesta del Router |
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
