# ARKOS Personal CEO OS — Roadmap

## Alcance y estado del roadmap

Las Fases 0–8 describen el recorrido original WhatsApp/n8n/Supabase. Sus marcas
historicas no acreditan un despliegue actual; por ejemplo Fase 0 figura completa
pero mantiene tareas pendientes. Los pilotos desktop/relay/chat estan en PRs
abiertos. Ver la [matriz de evidencia y propuesta descargable](ARKOS_DOWNLOADABLE_LIVE_VOICE_PROPOSAL.md)
antes de interpretar una capacidad como disponible.

La nueva linea de producto suma app propia PC/celular, voz live, permisos locales
y archivo privado durable por cliente. Se conserva el canal asincrono existente.

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

Esta fase trata mensajes de audio asincronos de WhatsApp. La voz en vivo dentro de
la app pertenece a la linea LV siguiente y requiere su propio contrato y pruebas.

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

**Ampliacion propuesta:** el producto descargable debe conservar un archivo local
durable del usuario, por proyectos/temas, incluso cuando use procesamiento cloud.
Obsidian sera una vista compatible de esos Markdown, no una dependencia ni la unica
salida del backend. Archivo, exportacion y recuperacion pasan a ser requisitos
transversales de LV1–LV4. El mirror Supabase original permanece como camino de
compatibilidad hasta diseñar y validar la migracion; este documento no la ejecuta.

| Tarea | Dependencia |
|-------|------------|
| Templates Markdown | Definidos |
| Daily notes automaticas | Summaries |
| Project notes | Items por proyecto |
| Meeting notes | Minutas |
| Decision log | Items tipo decision |
| Git sync opcional | Repo separado |

---

## Linea propuesta — ARKOS descargable, archivo propio y voz live

**Estado: diseño; sin fechas de lanzamiento ni tareas marcadas completas.**
Detalle, dependencias y criterios en la [propuesta de arquitectura](ARKOS_DOWNLOADABLE_LIVE_VOICE_PROPOSAL.md).

| Etapa | Resultado esperado | Puerta de salida |
|-------|--------------------|-----------------|
| LV0 | Reconciliar pilotos, permisos, modos y residencia de datos | Baseline revisada y una autoridad por tarea |
| LV1 | Contratos de voz y archivo portable, simulacion, exportacion | Compatibilidad, permisos, cancelacion e importacion/exportacion probados con datos sinteticos |
| LV2 | Voz local real y archivo por proyectos/temas en PC | Medicion y aceptacion humana, persistencia, backup/restauracion y limites de red |
| LV3 | Celular e hibrido opcional, sincronizacion elegida | Autenticacion, privacidad, conflictos, cuotas y recuperacion verificados |
| LV4 | Paquete por cliente y salida del servicio sin perder archivo | Otra PC/cliente, aislamiento, firma, actualizacion, desinstalacion y exportacion independiente |
| COM1 | Mensajeria entre personas, asistentes renombrables y push | Identidades/contactos, entrega con PC apagada, cifrado y bloqueo/revocacion |
| COM2 | Llamadas humanas app-a-app, separadas de voz IA | Aceptacion/rechazo, privacidad y pruebas de dispositivos/red |
| COM3 | Espacios personales/trabajo y grupos pequeños | Roles, invitaciones, claves, abuso y costes antes de escalar |
| Producto comercial | Ediciones gratis/pago, vinculacion guiada y packs por profesion | Licencias, compatibilidad y costes por usuario medidos antes de fijar precios |

No reemplaza ni fusiona los PR existentes. Procesamiento cloud, sincronizacion y
permisos son elecciones separadas; descargar una app no convierte los modelos cloud
en locales. Fiabilidad, memoria durable y distribucion requieren evidencia propia.

Direccion de mensajeria personal/trabajo aprobada por Jona el 2026-10-12. COM1–COM3
siguen pendientes de implementacion y revision tecnica; no autoriza merge o deploy.

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

