# WhatsApp Cloud API — Guia de Setup

## Prerequisitos

- Cuenta de Facebook/Meta con acceso a un Business Portfolio (INB / INB SAS)
- Acceso a developers.facebook.com

---

## Paso 1: Crear App en Meta Developers

1. Ir a https://developers.facebook.com/apps/
2. Click "Create App"
3. Seleccionar tipo: **Business**
4. Nombre: `ARKOS Personal OS`
5. Conectar al Business Portfolio de INB
6. Click "Create App"

---

## Paso 2: Agregar producto WhatsApp

1. Dentro de la app, ir a "Add Products"
2. Buscar **WhatsApp**
3. Click "Set Up"
4. Meta te lleva al panel de WhatsApp

---

## Paso 3: Obtener credenciales de prueba

En el panel de WhatsApp vas a ver:

| Campo | Donde encontrarlo |
|-------|-------------------|
| Temporary Access Token | WhatsApp > API Setup > "Generate" |
| Phone Number ID | WhatsApp > API Setup > "From" field |
| WhatsApp Business Account ID | WhatsApp > API Setup > header |
| Test Phone Number | Asignado automaticamente por Meta |

**Importante:** El token temporal dura 24 horas. Para produccion necesitas un System User Token permanente.

---

## Paso 4: Agregar numero de destino

1. En "To" field, agregar tu numero personal de WhatsApp
2. Meta te envia un codigo de verificacion por WhatsApp
3. Ingresar el codigo
4. Ahora podes enviar mensajes al numero de prueba

---

## Paso 5: Configurar Webhook

1. Ir a WhatsApp > Configuration > Webhook
2. Callback URL: `https://tu-n8n.com/webhook/arkos-whatsapp`
3. Verify Token: el mismo valor que pusiste en `.env` como `WHATSAPP_VERIFY_TOKEN`
4. Click "Verify and Save"
5. Suscribirse a: **messages**

### Como funciona la verificacion:

Meta envia un GET a tu URL con:
```
GET /webhook/arkos-whatsapp?hub.mode=subscribe&hub.verify_token=TU_TOKEN&hub.challenge=RANDOM_STRING
```

Tu webhook debe responder con el valor de `hub.challenge` y status 200.
El workflow de n8n ya maneja esto automaticamente.

---

## Paso 6: Probar envio de mensaje

Con curl:
```bash
curl -X POST "https://graph.facebook.com/v21.0/PHONE_NUMBER_ID/messages" \
  -H "Authorization: Bearer ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "to": "TU_NUMERO_CON_CODIGO_PAIS",
    "type": "text",
    "text": { "body": "Hola desde ARKOS" }
  }'
```

Si recibis el mensaje en tu WhatsApp, el setup funciona.

---

## Paso 7: Conectar con n8n

1. Activar el workflow `ARKOS_WHATSAPP_CLOUD_INBOX`
2. Copiar la URL del webhook de n8n
3. Pegarla en Meta > WhatsApp > Configuration > Webhook
4. Enviar un mensaje desde tu WhatsApp al numero de prueba
5. Verificar que n8n recibe el webhook

---

## Paso 8: Token permanente (antes de produccion)

1. Ir a Business Settings > System Users
2. Crear System User con rol Admin
3. Generar token con permisos:
   - `whatsapp_business_management`
   - `whatsapp_business_messaging`
4. Usar ese token en lugar del temporal

---

## Costos

| Concepto | Costo |
|----------|-------|
| Numero de prueba | Gratis |
| Mensajes en modo test | Gratis (limite bajo) |
| Mensajes servicio (produccion) | Variable por pais (~USD 0.005-0.08) |
| Mensajes utilidad | Variable por pais |
| Conversaciones iniciadas por usuario | Gratis las primeras 1000/mes |

Para ARKOS personal, el costo sera minimo porque es un solo usuario.

---

## Numero real (Fase posterior)

Cuando el flujo de prueba funcione:

1. Comprar chip/eSIM nuevo
2. Ir a WhatsApp Manager > Phone Numbers > Add
3. Verificar por SMS o llamada
4. Registrar en Cloud API
5. Display name: `ARKOS CEO`
6. Actualizar PHONE_NUMBER_ID en .env

---

## Troubleshooting

| Problema | Solucion |
|----------|----------|
| Webhook no verifica | Verificar que VERIFY_TOKEN coincide en Meta y n8n |
| No llegan mensajes | Verificar suscripcion a "messages" en Webhook fields |
| Token expirado | Generar nuevo o usar System User token |
| Error 400 al enviar | Verificar formato del numero (con codigo pais, sin +) |
| n8n no responde a tiempo | Meta espera respuesta <5 segundos, procesar async |
