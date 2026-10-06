# Validación del ETL

Extract, Transform, calidad/cuarentena y Load están implementados según el
[contrato integrado](../docs/design/etl-system/contract.md): nueve tablas, Parquet,
publicación completa en PostgreSQL, reejecución y scheduler de cinco minutos.
Las pruebas controladas y el [demo portable](../docs/demo-runtime.md) verifican entradas
sintéticas, consumo HTTP real, aislamiento, fallos, recuperación y persistencia.
La verificación histórica del organizador registrada en
[Extract](../docs/design/extract-card-support/verification-v1.md) acredita conservación
de bytes y estructura; no acredita por sí sola calidad de negocio ni evaluación de ML.
`make check` comprueba entorno/lint/formato y `make test` ejecuta las regresiones;
la prueba Compose/HTTP se ejecuta aparte en un proyecto desechable.

Para cada pipeline, implementa pruebas según su contrato de entrada y salida:

| Propiedad | Evidencia de aceptación |
| --- | --- |
| Contrato | Tipos, nulos, claves y dominios válidos; esquema incompatible detectado explícitamente |
| Reconciliación | Cada entrada tiene un destino o motivo de descarte; conteos y agregados se explican por las transformaciones |
| Precisión | Importes decimales y agregados comprobados por moneda; no sumar monedas distintas sin conversión definida |
| Integridad | Referencias huérfanas identificadas y tratadas según contrato |
| Historia | Snapshots distintos conservados aunque compartan clave de entidad |
| Idempotencia | Repetir la misma entrada no duplica filas ni cambia el resultado lógico publicado |
| Recuperación | Un fallo de carga deja intacta la última entrega completa; el reintento no duplica efectos |
| Actualizaciones | Llegadas tardías y correcciones procesadas según una política explícita |
| Linaje | Cada salida se vincula con entrada, ejecución y versiones de código y contrato |
| Escala | Duración, filas procesadas y memoria medidas sobre un volumen declarado |

Para pipelines que generen datasets de ML, añade aislamiento de particiones de entrenamiento
y evaluación según el contrato del consumidor. El benchmark de modelos y del servicio
conversacional no se ejecuta como parte del ETL.

Usa fixtures pequeñas, etiquetadas como generadas por el equipo, para fallos y reintentos.
Guarda métricas y manifiestos reales en `outputs/`, fuera de Git por defecto.
