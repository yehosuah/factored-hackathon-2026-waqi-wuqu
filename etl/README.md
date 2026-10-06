# Factored Hackathon 2026 - ETL
Repositorio de trabajo del ETL para el hackathon, basado en los documentos de `GeneralInfo/`.
Su responsabilidad es extraer, validar, transformar y entregar datos trazables para los consumidores
del proyecto. Incluye Python, herramientas de datos y configuración de los skills de desarrollo.
El servicio conversacional, la interfaz y la evaluación de modelos pertenecen al sistema consumidor.

El backend (BCK) se trabaja en el repositorio independiente
[FactoredAI_BCK](https://github.com/yehosuah/FactoredAI_BCK). Su checkout local está en
`FactoredAI_BCK/`; esa ubicación no lo convierte en un módulo del ETL. Cada repositorio
mantiene su propio entorno, pruebas, tickets y decisiones, y se integra mediante contratos de datos.

## Arranque

Requisito: [uv](https://docs.astral.sh/uv/getting-started/installation/) en el PATH.
Ejecuta desde la raíz del repositorio:

```bash
uv sync --locked
uv run --locked check-environment
```

`uv` usa Python 3.13.14, crea `.venv/` e instala las versiones de `uv.lock`.
Si Python no está disponible, `uv` puede descargarlo. La primera instalación requiere red;
las comprobaciones posteriores funcionan sin APIs externas ni credenciales.

Para verificar versiones bloqueadas, lint, formato y funcionamiento de las herramientas:

```bash
make check
```

Sin `make`, ejecuta:

```bash
uv lock --check
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked check-environment
```

La comprobación genera dos filas temporales del equipo, rechaza un importe inválido,
escribe y lee Parquet con Polars, y comprueba con DuckDB una suma decimal de 30.75.
Elimina los archivos temporales al terminar. `status: ok` verifica el entorno;
no valida el dataset del organizador ni una solución bancaria.

## Demo local sintética

La [guía de demo portable](docs/demo-runtime.md) inicia una entrega sintética completa
con PostgreSQL y el backend independiente, secretos privados y un adaptador stub
explícitamente identificado. No necesita datos del organizador ni modifica sus entradas.
Puede seleccionar el clasificador aprendido local del backend revisado mediante
`DEMO_CONVERSATION_ADAPTER=classifier`. La guía exige comprobar el modo efectivo en
el contenedor y en el descriptor de conversación; no confundir una entrega de datos
ML con un modelo cargado.

```bash
python3 scripts/demo.py up --backend-path ./FactoredAI_BCK
```

El API local usa `http://127.0.0.1:8010`; el frontend puede consumirlo mediante su proxy
same-origin `/api`. La guía incluye cuentas privadas y pruebas reales de publicación,
fallo, recuperación y persistencia tras reiniciar servicios.

## Evaluación del sistema

La [evaluación sintética del sistema](docs/system-evaluation.md) ejecuta 60 casos congelados
(30 ES y 30 PT) contra un demo desechable y un commit exacto del backend independiente:

```bash
uv run --locked --no-editable --reinstall-package factored-bank python scripts/evaluate_demo.py \
  --backend-path /path/to/FactoredAI_BCK --backend-sha <full-sha> \
  --run-id acceptance-01 --purpose acceptance
```

Publica resultados locales en `outputs/evaluation/`, con métricas de resolución segura,
automatización, contención, escalamiento, seguridad, latencia y coste. No entrena modelos
ni cambia el frontend. Consulta la guía para denominadores, limitaciones y prerequisitos.

## Herramientas

- Python 3.13 y `uv`: entorno y dependencias reproducibles.
- DuckDB: SQL local, sin servicio de base de datos.
- Polars: tablas y lectura diferida de Parquet.
- Pydantic: contratos explícitos de datos.
- Boto3: conexión S3 de solo lectura con inventarios y descargas condicionales.
- Ruff y pytest: formato, revisión estática y pruebas de comportamiento.
- JupyterLab e ipykernel: grupo opcional para exploración.

```bash
# Instalar y abrir notebooks localmente
make notebooks
# Alternativa sin make
uv sync --locked --group notebooks
uv run --locked --group notebooks jupyter lab notebooks
```

En el editor, selecciona `.venv/bin/python`. No se requiere activar el entorno con `uv run`.
Un `uv sync --locked` sin el grupo opcional puede retirar Jupyter; vuelve a incluir
`--group notebooks` para conservarlo.

## Estructura

```text
GeneralInfo/           PDF originales locales (fuera de Git)
src/factored_bank/     Código reutilizable y comprobación del entorno
data/raw/             Datos recibidos, sin modificar (fuera de Git)
data/processed/       Datos derivados (fuera de Git)
data/fixtures/        Datos de prueba locales (fuera de Git)
notebooks/            Exploración
evaluation/           Criterios de validación de los pipelines ETL
tests/                Regresiones ETL, profiler y demo con fixtures controladas
outputs/              Resultados y logs locales (fuera de Git)
docs/agents/          Gestor de issues y convenciones de dominio
docs/adr/             Decisiones de arquitectura
.scratch/             Trabajo e issues locales (fuera de Git)
CONTEXT.md            Glosario
AGENTS.md             Instrucciones para agentes
```

Lee [el contexto del reto](docs/hackathon-brief.md) y [el alcance del ETL](docs/etl.md).
El [alcance de soporte de tarjetas](docs/design/card-support-data.md) documenta las nueve
tablas, granularidad, relaciones y límites temporales. Los PDF originales y exports
generados se conservan como referencias locales fuera de Git.
Extract v1 está implementado con una CLI manual: planificación, adquisición inicial/incremental
y verificación local. El [contrato aceptado](docs/design/extract-card-support/extract-v1-contract.md)
rige esta implementación. El piloto, histórico,
repetición y verificación offline contra la entrega del organizador pasaron: 5,489 objetos,
1,265,179,481 bytes y 6,114,029 registros lógicos en el histórico. Consulta la
[evidencia de aceptación](docs/design/extract-card-support/verification-v1.md), separada de
las pruebas con fixtures y de cualquier validación futura de negocio.
Consulta la [guía operativa](docs/extract-operations.md) y las [convenciones de datos](data/README.md).
El origen S3 y la conservación local en `data/raw/` están acordados para Extract.
El [contrato ETL-BCK](docs/design/etl-system/contract.md) añade transformación de las nueve
tablas, cuarentena trazable, PostgreSQL y Parquet para consumidores, con backend independiente
y ejecución programada cada cinco minutos en Docker Compose.
El paquete conserva el nombre `factored_bank`.

El paquete ML es opcional: sin `--ml-root` ni `ETL_ML_ROOT`, el ETL entrega las nueve
tablas con `ml.readiness=not_included`. Para incluirlo, indica una ruta explícita;
si falta o es inválido, la ejecución falla. Compose lo incluye solo con
`-f compose.yaml -f compose.ml.yaml` y `ETL_ML_ROOT` configurado.
Consulta [opciones y compatibilidad](docs/etl-operations.md#optional-ml-pack-and-offline-preparation).

El [quick start para el ingeniero de ML](docs/ml-handoff.md) explica qué archivos enviar,
cómo clonar la entrega y cómo verificarla. La [entrega exploratoria para ML](docs/design/ml-handoff/review.md) reúne el histórico
raw verificado y casos/políticas sintéticos de revisión en español y portugués para
routing, retrieval y resúmenes. El paquete local portable pasó verificación en un
directorio independiente. Las anotaciones, traducciones y particiones de evaluación
todavía requieren revisión; no es una entrega de Transform validada para evaluación.

## Extract manual

Configura credenciales mediante un perfil AWS local o variables de proceso; no las agregues
a los comandos ni al repositorio. `verify` funciona sin credenciales ni conexión a S3.

```bash
uv run --locked factored-extract plan --scope pilot --pilot-date 2023-06-17
uv run --locked factored-extract run --scope pilot --pilot-date 2023-06-17
uv run --locked factored-extract verify --scope pilot --pilot-date 2023-06-17
```

Tras comprobar el piloto, usa `--scope full` para el histórico. Repetir `run` detecta novedades
y correcciones y reutiliza contenido revalidado. Cada entrega aceptada contiene las nueve tablas
en su alcance completo; los originales están en `data/raw/organizer/` y los manifiestos en
`outputs/extract/`. Esta CLI sigue siendo manual; `factored-etl` implementa las etapas
posteriores y el scheduler descritos en la guía integrada.

## Desarrollo y tickets

Agrega dependencias con `uv add <paquete>` o `uv add --dev <paquete>` y conserva ambos archivos
de configuración y lock. No uses `pip install` para modificar este entorno por fuera del lock.
Las pruebas de comportamiento se ejecutan con `make test` y usan datos inventados del equipo.
`make check` verifica el entorno, lint y formato; ambas comprobaciones son necesarias tras
cambios al pipeline. Ninguna requiere el dataset completo ni credenciales AWS.

`escribir-spec` y `partir-en-tickets` consultan `AGENTS.md` y `docs/agents/*.md`.
Puedes editar esos documentos directamente. Vuelve a ejecutar `configurar-desarrollo` solo
si cambias de gestor de issues.

La [guía de operación integrada](docs/etl-operations.md) explica Compose, secretos,
ejecución offline/viva, publicación, consumo ML y comprobaciones del backend.
Extract conserva su CLI y contrato propios; el pipeline completo usa `factored-etl`.

## Perfil de calidad del dataset

`uv run --locked factored-profile --release current` inspecciona los Parquet de la
entrega publicada, seleccionada mediante PostgreSQL. Para consumo portable usa
`--release <curated_release_id>`; ese modo funciona offline y no confirma publicación.
El profiler separa entradas, aceptados y rechazos del manifiesto, y calcula métricas
agregadas de nulos, categorías, tarjetas, textos repetidos y anomalías temporales.
Escribe `outputs/profiles/<curated_release_id>/profile.json` sin exponer registros.
Consulta [uso, requisitos y códigos de salida](docs/profile-operations.md).
