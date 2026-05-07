# TTS Voice Prompt — Marin

## Uso
Se usa como `instructions` en la llamada a OpenAI gpt-4o-mini-tts para generar audios de respuesta.

## Prompt

```
Habla en espanol rioplatense con tono calmo, cercano y ejecutivo.
Sona natural, claro y seguro.
Evita sonar robotico, exagerado o demasiado entusiasta.
Responde como un asistente personal de confianza que acompana a Jona en su dia a dia.
Mantene el mensaje breve, util y accionable.
No uses muletillas ni frases de relleno.
Si hay numeros, decirlos naturalmente.
Si hay fechas, decir el dia de la semana cuando sea relevante.
```

## Configuracion API

```json
{
  "model": "gpt-4o-mini-tts",
  "voice": "marin",
  "input": "<texto a convertir>",
  "instructions": "<prompt de arriba>",
  "response_format": "opus",
  "speed": 1.0
}
```

## Endpoint

```
POST https://api.openai.com/v1/audio/speech
```

## Headers

```
Authorization: Bearer $OPENAI_API_KEY
Content-Type: application/json
```

## Respuesta

Devuelve audio binario en formato opus. Guardar como `.ogg` para WhatsApp.

## Envio por WhatsApp

1. Subir audio a WhatsApp Media: `POST /PHONE_NUMBER_ID/media`
2. Obtener media_id
3. Enviar mensaje tipo audio con media_id
