# Distribución reproducible del piloto (2026-10-14)

## Decisión y alcance

Base elegida: PR #16, `claude/arkos-cloud-ui`,
`4f6f7c15ccbf3eed3c06b1589a0d961ba24bc68f`. Incorpora #15 y el arreglo de #14
mediante `6a08f48`; incluye #12/#13 sin repetirlos. El 14 de octubre se verificaron
#12/#14/#15/#16 con cuatro checks aprobados; #13 conserva un fallo histórico en
Windows 3.12. #17 es documental sobre main, no una integración del piloto.
Todos estaban abiertos como Draft. No se modifica ninguna de esas ramas.

Trabajo local autorizado: Windows 26200, PowerShell 7.6.5, Python 3.12.14
existente; checkout nuevo `C:\ArkosReview\windows-package-20261014`, rama
`codex/arkos-windows-package`. No hay AGENTS.md en el árbol de la base; se aplican
las reglas globales proporcionadas. Handoff versionado en lugar de Engram.
No se inspecciona ni modifica la instalación existente ni otros checkouts.

El cambio agrega distribución y reserva de espacio al preflight existente.
No modifica chat, aprobación/ejecución ni autoridad relay. Código Cloud heredado
incluido para conservar la base, pero sin configuración, SDK ni activación.
El launcher no pasa opciones Cloud ni Hermes; no hay proveedor sintético activo.
No se distribuye el agente relay ni su configuración: la pantalla ya lee snapshots
sin necesitarlo. No hay instalador autónomo ni modelos ni runtimes incluidos.

## Construcción

Requisitos del constructor: Git y Python 3.11+, ya instalados. Sin dependencias
de pip. Desde el checkout del commit que se quiere distribuir:

```powershell
python -B scripts/Build-ArkosPackage.py --output dist
python -B -m unittest discover -s tests -p test_windows_package.py -v
```

El constructor lee `packaging/windows-pilot.json` y archivos **del HEAD de Git**,
no del árbol de trabajo. Cambios sin commit no se empaquetan. La lista es explícita
y versionada: cualquier archivo nuevo requiere revisión. Rechaza enlaces, rutas
que escapen y duplicados. No recorre perfiles, datos o configuraciones locales.
No sobrescribe un ZIP existente. Para repetir, elegir otra carpeta de salida.

Versión piloto + SHA identifican cada ZIP. Orden, timestamps, permisos y bytes
se fijan; ZIP sin compresión evita diferencias entre versiones zlib. Archivos de
Git conservan sus bytes independientemente de autocrlf. El manifiesto lista los
archivos de contenido, tamaños, dependencias y hashes; SHA256SUMS cubre también
el manifiesto. El hash externo cubre todo el ZIP. No es una firma digital.

CI `Windows pilot package` compila el HEAD exacto del PR en Linux y Windows,
construye dos veces por plataforma, verifica igualdad y hashes, extrae a ruta
con espacios/acentos y prueba el launcher, centro y chat sintético contra la
copia extraída. Los fixtures se agregan solo al directorio temporal de tests;
no al ZIP. Windows prueba el launcher PowerShell y restauración del entorno.
Un job final compara los SHA-256 de Linux y Windows. Artefactos de CI duran
30 días; no son releases. La suite Desktop pilot heredada sigue verificando
Linux/Windows 3.11/3.12, relay y controles de seguridad. Su instalación del SDK
es exclusiva de CI; no se instala nada en la PC ni en el paquete.

Los procesos de aceptación usan loopback, datos temporales y cierre en finally.
No queda servidor permanente. La prueba manual se cierra con Ctrl+C en su consola.
No hay lint, typecheck ni build frontend configurados como gates independientes.

## Uso y aceptación

Las instrucciones incluidas con el ZIP están en [PILOT-WINDOWS.md](../../PILOT-WINDOWS.md).
Incluyen requisitos manuales, diagnóstico, inicio, cierre, retirada y segunda PC.
La aceptación en una segunda PC, modelos reales y velocidad siguen pendientes.
No confundir los tests sintéticos con una conversación real ni con certificación
de todas las versiones Windows/PowerShell. No se activa Cloud real.
