> Estado histórico de la preparación en #3. La rama de integración añade el lector real descrito en [RELAY_INTEGRATION.md](RELAY_INTEGRATION.md); sin configuración explícita conserva esta vista pendiente.

# Preparación de la vista remota — sin conectar el productor

Este incremento prepara la UI mientras Claude desarrolla el snapshot de lectura.
No define ni implementa su contrato de transporte. No lee el diario, archivos,
tokens o cuentas del agente; no consulta un relay ni concede permisos nuevos.

## Funciona ahora

- Las tarjetas locales indican **Solo esta PC**.
- La pantalla principal contiene una sección **Encargos del celular**, solo lectura.
- El endpoint privado `GET /api/remote-view` devuelve una proyección vacía con
  `sync_status=not_configured`. Está bajo la misma protección loopback que las
  demás lecturas. No contiene tareas simuladas en producción.
- `remote-view.js` valida y representa una **proyección interna de presentación**.
  El futuro adaptador debe traducir el contrato acordado a esta forma; el archivo
  publicado por Claude no se puede pasar directamente sin validar su contrato.
- Conserva nueve estados distintos. `claimed` significa reservada; nunca se
  etiqueta como si el efecto ya hubiera empezado. `unknown` requiere revisión y
  no ofrece un botón de reintento. `failed` se muestra como fallo sin inventar
  certezas adicionales sobre el efecto.
- Muestra fecha de la copia, información de PC desconocida y datos desactualizados.
  Fecha de sincronización y conectividad de la PC son conceptos separados.
- Si falla una consulta después de una copia válida, conserva la última vista
  marcada desactualizada. Si no hay copia, muestra que no hay información.
- Resultados remotos son solo metadatos o no disponibles. No se inventa un enlace
  de descarga ni se abre una ruta recibida.
- No mezcla avisos/cuentas remotos con las estadísticas ni con la cola local.
  El lector tiene cero botones de aprobación, ejecución, reserva o descarga.

## Forma interna v1

```json
{
  "projection_version": 1,
  "sync_status": "not_configured",
  "device_status": "unknown",
  "last_sync": null,
  "tasks": []
}
```

`sync_status`: `not_configured`, `current`, `stale`, `unavailable`.
`device_status`: `unknown`, `online`, `offline`, solo con señal documentada del
productor. No inferir "PC online" porque una copia se actualizó.

Cada tarea se representa con `id`, `title`, `state`, `updated_at`,
`result_summary`, `result_availability` (`metadata_only` o `not_available`).
La UI fija `origin=relay`. Todos los textos se pintan con `textContent`.
La proyección elimina campos extra; no requiere credenciales, payloads completos
ni rutas absolutas. Límite inicial: 500 tarjetas, títulos de 180 caracteres,
resúmenes de 2000. Estos son límites de presentación, no límites del relay.

## Después de la entrega de Claude

1. Revisar su contrato exacto y las garantías de usuario/dispositivo, atomicidad,
   límites, fechas, reinicios y ausencia de secretos en el snapshot.
2. Implementar un lector de solo lectura explícitamente configurado y un adaptador
   en el backend. Mantener credenciales fuera de HTTP/JS. No descubrir archivos
   automáticamente ni asumir que journal.sqlite3 contiene toda la cola.
3. Decidir cuándo una copia es stale conforme al contrato; la UI actual **no tiene
   un umbral arbitrario de antigüedad**. No presentar una fase del diario como un
   estado canónico actualizado del relay.
4. Probar con el productor real: pendientes no entregadas, reconexión, escritura
   interrumpida, aislamiento, snapshot inválido y ejecución simultánea del agente
   y el worker local. No sintetizar aprobaciones ni insertar tareas en Queue.
5. Después acordar vista de detalles/resultados, cuentas y operaciones remotas.

## Pruebas y límites

`node scripts/Test-ArkosRemoteView.cjs` prueba los nueve estados, IDs duplicados,
fechas inválidas, estados incompatibles, descarga no autorizada y descarte de
campos sensibles. El E2E de navegador usa **un transporte sintético controlado**
para verificar render de pendientes/reservadas/inciertas, texto malicioso,
datos stale y cero POST al consultar. No demuestra que exista sincronización real.

La UI funcional de producción sigue indicando **Conexión pendiente**. Las
capturas ordinarias reflejan ese estado. Las tarjetas remotas sintéticas solo
existen durante pruebas y no son datos de Jona.
