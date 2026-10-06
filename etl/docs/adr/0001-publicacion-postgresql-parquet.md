# 0001 - Publicación PostgreSQL y Parquet

**Estado:** aceptada, acordada con el usuario el 2026-10-01.

## Contexto

Backend y ML necesitan la misma entrega validada. El backend requiere publicación
transaccional y estado de simulación concurrente; ML requiere archivos portables.
El usuario pidió repositorios e imágenes separados unidos por Docker Compose.

## Decisión

Publicar las nueve tablas en PostgreSQL mediante versiones inmutables y un único
puntero actualizado tras reconciliar toda la carga en una transacción. Exportar
también Parquet, rechazos, manifiestos y datasets ML de revisión. DuckDB es una
herramienta local de transformación; PostgreSQL es el almacén del backend.
Los roles ETL y backend tienen esquemas y permisos distintos.

## Alternativas consideradas

Un archivo DuckDB compartido no aporta el modelo transaccional de servicio y permisos
por rol acordado. Solo PostgreSQL dificulta la entrega portable a ML. Una sola imagen
mezclaría los ciclos de vida de dos repositorios independientes.

## Consecuencias

Una carga parcial no cambia la entrega aceptada. Las correcciones conservan versiones
previas. Mantener PostgreSQL y archivos requiere almacenamiento adicional, secretos
de runtime y una política operativa de conservación futura.
