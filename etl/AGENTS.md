# Instrucciones del repositorio

## Modo de trabajo

Para trabajo sustancial, usa `achiever-mode` y `toolkit:afinar`. Si falta contexto,
usa `plan-de-sesion`. Aplica proporcionalidad: las tareas triviales siguen siendo triviales.
Determina el resultado buscado, ejecuta, valida y cierra los pasos razonables dentro del alcance.

## Desarrollo

- Este repositorio contiene el ETL: extracción, transformación, calidad y carga de datos.
- El backend se desarrolla en el repositorio independiente `FactoredAI_BCK`, cuyo checkout
  local está en `FactoredAI_BCK/`. Su `AGENTS.md` define su configuración; el entorno y los
  comandos de este ETL no se aplican al BCK. Mantén tickets y decisiones separados.
- Lee `README.md`, `CONTEXT.md`, `docs/etl.md` y `docs/hackathon-brief.md` antes de trabajo sustancial.
- Usa Python 3.13 y `uv`; conserva `uv.lock` junto con `pyproject.toml`.
- Ejecuta `make check` tras cambios al entorno o código. Ejecuta pruebas pertinentes cuando existan.
- El código reutilizable vive en `src/factored_bank/`; los notebooks son exploratorios.
- Identifica explícitamente fixtures del equipo, datos del organizador y métricas simuladas.
- No publiques datasets, credenciales ni registros individuales. Los datos locales van en `data/`.
- Conserva entradas originales y distingue fecha del evento, fecha de proceso y fecha de ingesta.
- Define claves, granularidad, tipos, nulos y reglas de deduplicación antes de transformar una tabla.
- No dedupliques snapshots históricos solo por la clave de entidad ni rellenes importes nulos sin regla.
- Verifica reconciliación, idempotencia y publicación completa antes de declarar una carga exitosa.
- Registra fuentes, checksums, versión de código/contrato, conteos y resultado por ejecución.
- Confirma origen, destino y estrategia de carga antes de implementar conexiones o pipelines.
- El servicio conversacional, modelos e interfaz corresponden a consumidores de los datos del ETL.

## Skills de desarrollo

### Gestor de issues

Issues locales en `.scratch/`. Ver `docs/agents/gestor-de-issues.md`.

### Dominio

Glosario único en `CONTEXT.md` y decisiones en `docs/adr/`.
Ver `docs/agents/dominio.md`.
