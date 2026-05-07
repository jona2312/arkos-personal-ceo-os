# Checklist — Fase 1: MVP Conversacion Basica

## Objetivo
```
Jona escribe por WhatsApp -> ARKOS recibe -> clasifica -> guarda -> responde
```

---

## Pre-requisitos

- [ ] Cuenta Meta Developers activa
- [ ] App "ARKOS Personal OS" creada (tipo Business)
- [ ] Producto WhatsApp agregado a la app
- [ ] Business Portfolio conectado (INB)
- [ ] Numero de prueba visible en el panel
- [ ] Token temporal generado
- [ ] Numero personal de Jona agregado como destinatario de prueba
- [ ] Proyecto Supabase creado
- [ ] Migrations ejecutadas (001 a 009)
- [ ] n8n operativo y accesible por URL publica
- [ ] Credencial OpenAI activa
- [ ] .env configurado con todos los valores

---

## Setup Webhook

- [ ] Workflow `ARKOS_WHATSAPP_CLOUD_INBOX` importado en n8n
- [ ] Workflow activado
- [ ] URL del webhook copiada
- [ ] Webhook configurado en Meta > WhatsApp > Configuration
- [ ] Verify Token coincide entre Meta y n8n
- [ ] Verificacion exitosa (Meta muestra "Verified")
- [ ] Suscripcion a campo "messages" activa

---

## Test: Envio desde API

- [ ] Enviar mensaje de prueba con curl desde terminal
- [ ] Mensaje llega al WhatsApp de Jona
- [ ] Respuesta 200 de la API

```bash
curl -X POST "https://graph.facebook.com/v21.0/PHONE_NUMBER_ID/messages" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "to": "NUMERO_JONA",
    "type": "text",
    "text": { "body": "ARKOS online. Test inicial." }
  }'
```

---

## Test: Recepcion en n8n

- [ ] Jona envia mensaje al numero de prueba
- [ ] n8n recibe el webhook (visible en Executions)
- [ ] Parse WhatsApp Message extrae datos correctamente
- [ ] No hay error en la ejecucion

---

## Test: Guardado en Supabase

- [ ] Mensaje guardado en tabla `arkos_messages`
- [ ] Campos correctos: from_phone, text_content, message_type, direction='inbound'
- [ ] created_at con timestamp correcto

---

## Test: Clasificacion con OpenAI

- [ ] ARKOS CEO Router recibe el texto
- [ ] Responde JSON valido
- [ ] Intent clasificado correctamente
- [ ] confirmation_message generado

### Pruebas de clasificacion:

| Input | Intent esperado | Department |
|-------|----------------|------------|
| "Recordame manana llamar al contador" | create_items | agenda_ops |
| "Que tengo hoy" | query | agenda_ops |
| "Anota: reunion con inversores el viernes" | create_items | agenda_ops |
| "Este gasto es de la empresa" | create_items | finance_control |
| "Haceme un resumen de los mails" | query | docs_comms |
| "Buen dia Arkos" | chat | ceo |

---

## Test: Respuesta por WhatsApp

- [ ] ARKOS responde por texto a Jona
- [ ] Respuesta llega al WhatsApp de Jona
- [ ] Mensaje coherente y natural
- [ ] No hay errores 400/401 en el HTTP Request

---

## Test: Flujo completo end-to-end

- [ ] Jona envia: "Arkos, recordame el viernes pagar la factura de internet"
- [ ] n8n recibe
- [ ] Mensaje guardado en Supabase
- [ ] Router clasifica como create_items / reminder / agenda_ops
- [ ] ARKOS responde: "Listo, Jona. Recordatorio creado: pagar factura de internet el viernes."
- [ ] Respuesta llega a WhatsApp

---

## Validacion de seguridad basica

- [ ] Token de WhatsApp NO esta hardcodeado en el workflow (usar credenciales n8n)
- [ ] SUPABASE_SERVICE_ROLE_KEY NO expuesto
- [ ] Webhook solo procesa mensajes del numero de Jona (filtro basico)
- [ ] No se envian mensajes a terceros sin aprobacion

---

## Metricas de exito Fase 1

| Metrica | Criterio |
|---------|----------|
| Latencia respuesta | < 10 segundos |
| Tasa de error | < 5% |
| Clasificacion correcta | > 80% en pruebas manuales |
| Mensajes guardados | 100% de inbound |
| Uptime webhook | Sin caidas durante pruebas |

---

## Siguiente paso: Fase 2

Una vez que TODOS los items de este checklist esten marcados, avanzar a:
- Recepcion de audio
- Transcripcion
- Respuesta con voz Marin

No avanzar si Fase 1 no esta completa.
