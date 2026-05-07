# ARKOS — Test Plan Workflows v2

## Pre-requisitos

- [ ] Supabase: proyecto creado, migrations 001-010 ejecutadas
- [ ] n8n: 7 workflows importados y activos
- [ ] n8n: variables de entorno configuradas
- [ ] Meta: webhook configurado con verify token
- [ ] Meta: suscripcion a campo "messages" activa

---

## Test 1 — Verify Token (webhook Meta)

**Accion:** Configurar webhook en Meta con URL y verify token.

**Esperado:**
- Meta envia GET con hub.mode=subscribe + hub.verify_token
- n8n valida token contra WHATSAPP_VERIFY_TOKEN
- Si coincide: responde hub.challenge con 200
- Si no coincide: responde 403
- Meta muestra "Verified"

---

## Test 2 — Canal basico (Hola Arkos)

**Mensaje:** `Hola Arkos`

**Esperado:**
- INBOX recibe webhook POST
- Parse & Validate extrae mensaje
- Valida numero autorizado (AUTHORIZED_OWNER_PHONE)
- Guarda inbound en arkos_messages
- Llama a CEO Agent
- CEO Agent clasifica intent=chat, department=ceo
- No guarda items (es chat)
- Responde saludo natural
- Guarda outbound en arkos_messages
- Mensaje llega a WhatsApp de Jona

**Verificar en Supabase:**
- 2 registros en arkos_messages (inbound + outbound)
- 0 registros nuevos en arkos_items

---

## Test 3 — Memoria: guardar (recordatorio)

**Mensaje:** `Arkos, recorda que el sabado tengo el cumple de un amigo`

**Esperado:**
- CEO Agent clasifica intent=create_items, department=agenda_ops
- Crea item tipo reminder o note con fecha del sabado
- Guarda en arkos_items
- Responde confirmando

**Verificar en Supabase:**
- 1 registro nuevo en arkos_items con item_type=reminder o note
- title contiene "cumple" o "amigo"
- due_date o content contiene referencia al sabado

---

## Test 4 — Memoria: recuperar

**Mensaje (al dia siguiente o en otra ejecucion):** `Arkos, que tenia el sabado?`

**Esperado:**
- CEO Agent ejecuta search_memory
- Encuentra item del cumpleanos
- Responde con contexto: "El sabado tenes el cumple de un amigo"

**Este es el test clave.** Si pasa, ARKOS tiene memoria real.

**Verificar en n8n:**
- Nodo "Search Memory" retorna resultados
- Nodo "Enrich with Memory" incluye contexto en el prompt

---

## Test 5 — Numero no autorizado

**Desde otro numero:** `Hola`

**Esperado:**
- Parse & Validate detecta numero no autorizado
- skip=true, reason=unauthorized_number
- No llama a OpenAI
- No consume tokens
- Responde 200 a Meta (para evitar reintentos)
- No guarda en arkos_messages (opcional: guardar log minimo)

---

## Test 6 — Aprobacion

**Mensaje:** `Arkos, mandale un WhatsApp a Oscar diciendo que manana vemos lo de la matricula`

**Esperado:**
- CEO Agent detecta requires_approval=true
- Crea registro en arkos_approvals con status=pending
- NO envia mensaje a Oscar
- Responde a Jona: "Jona, esto requiere tu aprobacion. Queres que le mande a Oscar...?"

**Verificar en Supabase:**
- 1 registro nuevo en arkos_approvals con status=pending
- action_type y action_description correctos

---

## Test 7 — Tarea con prioridad

**Mensaje:** `Arkos, anota tarea urgente: revisar contrato de alquiler antes del viernes`

**Esperado:**
- intent=create_items, department=agenda_ops
- item_type=task, priority=high o urgent
- due_date=viernes proximo
- Guarda en arkos_items
- Confirma tarea creada

---

## Test 8 — Nota simple

**Mensaje:** `Arkos, anota que el numero de tracking del paquete es ABC123456`

**Esperado:**
- intent=create_items, department=ceo
- item_type=note
- Guarda en arkos_items
- Confirma nota guardada

---

## Test 9 — Consulta de pendientes

**Mensaje:** `Arkos, que tengo pendiente?`

**Esperado:**
- intent=query, department=agenda_ops
- Search Memory busca items activos/pending
- Responde con lista de pendientes desde Supabase

---

## Test 10 — Error handling

**Accion:** Apagar temporalmente OpenAI API key

**Esperado:**
- CEO Agent falla al llamar a OpenAI
- Parse CEO Response usa fallback
- Responde: "Perdon Jona, tuve un problema..."
- No crashea el workflow
- Responde 200 a Meta

---

## Metricas de exito

| Metrica | Criterio |
|---------|----------|
| Latencia respuesta | < 15 segundos |
| Tasa de error | < 5% |
| Memoria guardada | 100% de create_items |
| Memoria recuperada | > 80% en busquedas simples |
| Mensajes guardados | 100% inbound + outbound |
| Numero no autorizado | 100% bloqueado |
| Aprobaciones | 100% creadas sin ejecutar |

---

## Orden de ejecucion

1. Test 1 (verify token)
2. Test 5 (numero no autorizado)
3. Test 2 (hola basico)
4. Test 3 (guardar memoria)
5. Test 4 (recuperar memoria)
6. Test 6 (aprobacion)
7. Test 7-9 (variaciones)
8. Test 10 (error handling)
