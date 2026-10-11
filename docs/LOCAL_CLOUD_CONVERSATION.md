# Un ARKOS, dos formas de procesamiento

Estado: base de integración. Local conserva HermesBridge; Cloud NO está implementado.
Este documento y su selector no prueban una conexión a Qwen ni aislamiento del sistema operativo.

## Lo que cambia ahora

`arkos_pilot.providers.ConversationProvider` define el método que consume el chat:
`converse(request, cancel_event=None) -> response`. El formato v1 y los límites
siguen en `arkos_hermes.contract`, conservando compatibilidad con el runner Python
privado de Hermes. No se duplican el contrato, la cola ni las aprobaciones.

El centro resuelve la configuración antes de crear estado o abrir un socket:

| Selección interna | Resultado actual |
|---|---|
| `hermes`, con bridge | Modo existente `hermes`, procesamiento declarado `local` |
| `synthetic`, con bridge | Prueba explícita, procesamiento `synthetic` |
| modo válido, sin bridge | `unconfigured`; no inventa respuestas |
| `cloud`, con o sin bridge | Rechazo explícito: implementación pendiente |
| cualquier otro modo | Rechazo explícito |

Los nombres existentes `hermes` y `synthetic` permanecen compatibles. El estado
HTTP del chat añade `processing`; no incluye rutas, claves, endpoint ni mensajes.
La etiqueta describe la configuración del adaptador confiado, no demuestra dónde
corre código arbitrario. No se admiten plugins ni adaptadores por entrada HTTP.

No existe fallback: la caída del seleccionado termina en error. No se prueban
claves del entorno ni se elige otro proveedor. La respuesta sigue validándose en
Conversations; fallas y cancelaciones no conservan contenido aprovechable.
El selector no es un firewall ni una validación de seguridad de código de terceros.

## Contrato obligatorio para el adaptador Cloud futuro

1. Reutilizar v1, historial acotado, timeout, cancelación y validación del chat.
2. Devolver texto y propuestas, sin autoridad para aprobar ni ejecutar.
3. Crear tarea pendiente únicamente por la acción humana actual. Conservar el
   recibo transaccional e idempotencia. El relay sigue de solo lectura.
4. Configuración Cloud explícita. Consentimiento comprensible sobre proveedor,
   datos enviados y retención. No enviar conversaciones locales anteriores al
   cambiar de modo sin selección explícita de contexto; nueva sesión por defecto.
5. Cliente sin clave maestra del proveedor. Servicio autenticado con secretos del
   servidor, cuota por usuario y presupuesto reservado antes de la llamada. No
   confiar en contadores del cliente. Conciliar consumo real y no duplicar gasto
   por reenvío de la misma solicitud. Una respuesta perdida queda incierta; no
   implica devolución del gasto ni permiso para repetir la llamada pagada.
6. Límites de entrada, salida, duración y concurrencia. Agotar presupuesto debe
   impedir una llamada adicional. Registrar solo métricas necesarias y sanitizadas.
7. Cancelar debe impedir que una respuesta tardía cree propuestas utilizables.
   No prometer que cancelar elimina el consumo que el proveedor ya procesó.
8. Streaming, voz y búsqueda externa requieren sus propios contratos y medición;
   no anunciar estas capacidades por haber conectado texto.
9. Cualquier cambio de proveedor o fallback necesita política explícita aceptada.
   Local estricto no permite fallback cloud. No etiquetar nube como datos públicos
   ni prometer privacidad absoluta al procesamiento local.
10. Añadir implementación, pruebas y aceptación antes de habilitar `cloud` en el
    selector. Una etiqueta nueva o una variable de entorno no lo habilita.

## Próximo cierre: piloto local real (Codex en Windows)

Usar la rama más reciente revisada y consultar `docs/HERMES_BRIDGE.md` y
`docs/task-center/CONVERSATION_ACCEPTANCE_2026-10-09.md` para comandos existentes.
La creación del perfil dedicado dentro de D:\ARKOS sigue su autorización específica;
este PR no la concede ni modifica perfiles.

Criterios de salida:
- Identificar versiones, rutas y cambios preexistentes sin leer secretos.
- Conversar con el modelo real y medir duración de varios turnos en español.
- Crear una propuesta, convertirla en tarea pendiente, aprobar y ejecutar mediante
  acciones distintas, verificar el archivo. No aceptar respuestas sintéticas.
- Cancelar un turno real; comprobar que no llega contenido aprovechable después.
- Sin modelo local, mostrar indisponibilidad y ninguna derivación a nube.
- Capturar evidencia sanitizada y explicar cierres/limpieza. No medir sólo CI.

## Trabajo independiente para Claude

Revisar el contrato y proponer el adaptador cloud/servidor de cuotas mediante un
Draft PR separado, con transporte simulado y sin llamadas pagas. Antes de código
productivo, concretar proveedor, autenticación, presupuesto, almacenamiento,
consentimiento y recuperación de respuestas perdidas. No cambiar la rama del
piloto local ni duplicar conversaciones/aprobaciones.

## Entrega descargable

Después del piloto real: paquete Windows en otra PC, selección de modo, requisitos
medidos del modelo local, modelo descargable opcional con licencia comprobada,
actualización/desinstalación, diagnóstico sin secretos y soporte documentado.
No hay todavía instalador, planes comerciales, login cloud ni suscripciones.
La medición del consumo precede a fijar precios o prometer uso ilimitado.

## Validación de esta entrega

`python -B -m unittest discover -s tests -p test_provider_selection.py -v`

Siete pruebas: compatibilidad local/sintética, ausencia de configuración, bloqueo
de cloud/auto antes de socket o estado, adaptador inválido, error sin fallback y
rechazo de contenido en respuesta fallida. Todas usan proveedores sintéticos en
memoria. La suite existente verifica HTTP, cola y puente de proceso.
