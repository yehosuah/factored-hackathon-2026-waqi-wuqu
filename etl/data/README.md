# Datos locales

Las tablas del organizador se adquieren localmente mediante Extract y no se versionan en Git.
Que exista una carpeta raw no demuestra que contenga una entrega completa aceptada.

- `raw/organizer/`: bytes originales por SHA-256; los manifiestos conservan claves de fuente,
  particiones y procedencia. `objects/` contiene originales, `staging/` evidencia parcial y
  `current/` punteros separados por alcance piloto/histórico.
- `processed/`: salidas locales regenerables de transformaciones posteriores; no implica que
  este directorio sea el destino final de carga del ETL.
- `fixtures/`: pruebas generadas por el equipo, siempre diferenciadas del dataset del organizador.

El contenido de estas carpetas está ignorado por Git. Extract acepta el dialecto CSV y los
encabezados versionados de las nueve tablas; conserva cambios incompatibles como evidencia sin
publicarlos. Los manifiestos en `outputs/extract/` registran origen, identidad, fechas y checksum.
Revisa permisos de uso antes de publicación
o envío a servicios externos. No agregues credenciales a esta carpeta.

Los contratos y las reglas de transformación se versionan junto al código; los datos y los
manifiestos de ejecución permanecen locales. Para cada entrega conserva la granularidad,
partición o snapshot de origen. Distingue fechas de evento, proceso e ingesta.
No sobrescribas un snapshot anterior para resolver duplicados sin una regla acordada.

Los rechazos deben conservar su motivo y referencia de origen en una ubicación local definida
por el pipeline. Las salidas parciales no deben presentarse a consumidores como cargas completas.
Consulta [el contrato mínimo de un pipeline](../docs/etl.md).

Consume una entrega a través de su manifiesto aceptado y de `factored-extract verify`, nunca
enumerando archivos arbitrarios en raw. Una corrección crea otra versión; una desaparición remota
requiere revisión y no borra la historia local. No hay eliminación automática de historial ni
publicación de archivos parciales. Consulta la [guía operativa](../docs/extract-operations.md).

Para revisar que un archivo está ignorado: `git check-ignore -v data/raw/<archivo>`.
