# Pruebas

Ejecuta `make test` o `uv run --locked pytest`. La suite de Extract usa fuentes controladas,
respuestas S3 simuladas y archivos temporales inventados por el equipo. No necesita credenciales,
acceso a S3 ni registros del organizador. Para entorno, lint y formato usa `make check`.

La interfaz primaria de prueba es el coordinador que usa la CLI. Se verifican planificación,
publicación completa, reutilización, llegadas tardías, correcciones, aislamiento del piloto,
integridad local y bloqueo de entregas inválidas. Las pruebas del adaptador S3 verifican solicitudes
condicionales, paginación y reintentos; las de validación cubren estructura CSV; las de almacenamiento
cubren bloqueos, rutas seguras y fallos alrededor del punto de publicación.

La evidencia contra el organizador —piloto, histórico completo, repetición y verificación— se
registra aparte en los resultados locales de `outputs/extract/`. Las cuatro comprobaciones
pasaron; véase el [informe de aceptación](../docs/design/extract-card-support/verification-v1.md).
La suite final tiene 100 pruebas y `make check` pasa. Que pasen estas fixtures no
certifica calidad de negocio ni completitud del origen. No se prueban todavía Transform, Load
ni operaciones bancarias del backend. Los criterios generales están en `evaluation/README.md`.
