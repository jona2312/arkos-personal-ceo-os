# Conversación en portada — contrato y aceptación

Repositorio jona2312/arkos-personal-ceo-os; rama codex/arkos-conversation-home.
Base fijada del PR #9: 2b3f6a5c5b5e300ca5d7c4ec927af5b8e6a1d5c4.
Incluye #8; no se reaplica ni se modifica ninguna de esas ramas.

Objetivo: corregir presencia/valor del entorno del launcher y llevar conversación
escrita, historial y propuestas a la portada neuronal. Terminado cuando hay
regresiones de seguridad/concurrencia/idempotencia, aceptación Windows, capturas,
CI y PR Draft sobre #9. Sin editar D:\ARKOS, perfiles, voz, servicios o infraestructura.
Engram no está disponible entre las herramientas de esta sesión; este documento
y el registro de aceptación versionado son el handoff sanitizado.

## Contrato

- Sin configuración explícita: Hermes por conectar, sin respuesta de sustitución.
- Un turno activo por servidor; hasta 64 IDs por sesión, sin expulsar recibos para
  aceptar reenvíos ambiguos. Mismo ID y pedido: misma ejecución/respuesta. Otro
  contenido con el mismo ID: rechazo. Cola y consultas HTTP siguen independientes.
- POST /api/chat recibe el contrato v1 de HermesBridge; GET /api/chat informa
  disponibilidad/turno activo; GET /api/chat/{id} permite consultar sin bloquear.
- POST /api/chat/{id}/cancel con objeto vacío solicita cancelación cooperativa.
  La señal llega también si el proceso aún no se registró. Cierre del servidor
  señala cancelación y espera a los trabajadores. No es un servicio persistente.
- POST /api/chat/{id}/note solo admite proposal_id. Busca la propuesta en el
  servidor, revalida contrato y contenido y crea una nota awaiting_approval.
  No acepta texto, aprobación ni acciones elegidas por el cliente. La tabla
  task_sources conserva la relación con la tarea en la misma transacción SQLite,
  para que un doble clic/reenvío no genere otra nota.
- Errores/cancelación/timeout no contienen propuestas utilizables. Los diagnósticos
  internos del runner no se envían a la pantalla.
- Autenticación local, Host/Origin y lectura remota permanecen iguales. Chat limita
  el cuerpo a 200 kB y hereda los límites semánticos del contrato. Historial acotado,
  solo user/assistant; no roles privilegiados desde el navegador.
- Los textos del modelo se insertan como texto, nunca HTML. Esperar al modelo
  cambia data-chat; ejecutar una tarea cambia data-activity. Son señales distintas.

## Matriz de aceptación

Regresiones: launcher ausente/vacío/valor por éxito, exit no cero y excepciones;
chat sin configurar; respuesta e historial; consultas de tareas durante espera;
cancelación inmediata y tardía; timeout/error/salida inválida; cierre de procesos;
concurrencia y doble envío; propuestas manipuladas; nota pendiente e idempotencia;
autenticación/Host/Origin/tamaño/roles; XSS visual; nueve estados relay conservados.

Navegador a 100 %, escritorio y viewport móvil medido; Dorado y rojo, Intenso,
Completo, Ligero, pausa y movimiento reducido. Runner sintético explícito para
aceptación, sin importar Hermes ni conectar Qwen. La evidencia sintética nunca
certifica calidad, latencia ni disponibilidad del modelo real.
