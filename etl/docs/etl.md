# Alcance y contratos del ETL

Este repositorio es el ambiente de trabajo del ETL de LATAM Bank. El stack y la comprobación
del entorno están instalados y Extract v1 tiene una implementación manual. El usuario autorizó
Transform, Load, scheduling en Docker y la integración con el backend el 2026-10-01.
El [contrato integrado](design/etl-system/contract.md) rige esas etapas y la
[guía operativa](etl-operations.md) documenta su ejecución.

Los [contratos propuestos para ML](design/ml-handoff/README.md) y la
[entrega exploratoria](design/ml-handoff/review.md) añaden un paquete local portable
con raw y fuentes sintéticas de revisión para tres experimentos. Su verificación de
consumo no acredita etiquetas, traducciones ni una evaluación de modelos; las reglas
de Transform para los datos del organizador están declaradas en el contrato integrado;
las etiquetas y las traducciones del paquete ML conservan estado de revisión pendiente.

El [alcance de soporte de tarjetas](design/card-support-data.md) documenta las nueve
tablas, sus relaciones y las restricciones temporales para los consumidores.
El [contrato aceptado de Extract v1](design/extract-card-support/extract-v1-contract.md) es la
base vigente. La [guía operativa](extract-operations.md)
describe la CLI implementada. Las pruebas controladas y las ejecuciones contra el organizador
son evidencias distintas. El usuario aprobó avanzar a Transform y Load tras revisar
un Extract funcional.

## Responsabilidad

Entregar datos reproducibles, trazables y con calidad explícita a los consumidores del proyecto.
El servicio de atención bancaria, la interfaz y los modelos consumen esas entregas.
El enunciado completo sigue disponible en `hackathon-brief.md` como contexto del equipo.

El backend se desarrolla aparte en `https://github.com/yehosuah/FactoredAI_BCK`, con checkout
local en `FactoredAI_BCK/`. Tiene código, entorno, pruebas, tickets y decisiones propios.
La integración ETL-BCK se acuerda mediante contratos de datos; la ubicación local de ambos
checkouts no crea una dependencia de ejecución entre sus carpetas.

## Implementación de Extract v1

El origen acordado es S3, bajo `data/` en el bucket del organizador, en `us-east-2`. Se ingieren
clientes, productos, sucursales, agentes de servicio, transacciones, interacciones, transcripciones,
reclamos y encuestas. Los CSV originales quedan en almacenamiento local por SHA-256, con
manifiestos completos y versiones conservadas. Un piloto separado precede al histórico completo.

`factored-extract plan` persiste el inventario sin descargar objetos completos. `run` realiza
adquisición inicial o incremental y solo publica tras reconciliar el inventario y validar todos
los objetos. `verify` comprueba una entrega local sin contactar S3. Desapariciones, cambios de
esquema o cambios de fuente durante la ejecución impiden aceptar la entrega candidata.

La validación de Extract comprueba estructura CSV y conservación de bytes; no aplica reglas
de negocio, convierte tipos ni deduplica. Las pruebas controladas y la adquisición real del
piloto, histórico, repetición y verificación offline pasaron. La
[evidencia de aceptación](design/extract-card-support/verification-v1.md) registra 5,489 objetos,
1,265,179,481 bytes y 6,114,029 registros lógicos; la repetición reutilizó todo sin descargas.
Extract conserva su CLI manual. `factored-etl serve` añade ejecución cada cinco minutos
y reconciliación diaria; la consulta viva a S3 requiere credenciales de runtime.

## Contrato mínimo por pipeline

Versionar el contrato junto al código antes de implementar la transformación:

| Elemento | Qué especificar |
| --- | --- |
| Origen | Tabla, ubicación lógica, formato, versión y particiones disponibles |
| Granularidad | Qué representa una fila y cómo se distingue una entidad de un snapshot |
| Esquema | Campos, tipos, precisión decimal, campos anulables y valores permitidos |
| Identidad | Clave única efectiva, claves foráneas y alcance temporal de cada clave |
| Transformación | Reglas de normalización, filtros, deduplicación y desempate verificable |
| Calidad | Comprobaciones, umbrales acordados, condiciones que bloquean y tratamiento de rechazos |
| Tiempo | Semántica de evento/proceso/ingesta, zona horaria y llegadas tardías |
| Carga | Destino, estrategia de reemplazo o actualización y publicación de una entrega completa |
| Reejecución | Identidad de entrada, comportamiento ante repetición, correcciones y recuperación |
| Consumo | Esquema de salida, particionado, disponibilidad y compatibilidad con consumidores |

La definición de campos del diccionario es un punto de partida, no evidencia de que los datos
cumplen el contrato. Los porcentajes de duplicados y nulos declarados no son umbrales de aceptación.

## Registro de ejecución

Guardar por ejecución un manifiesto en `outputs/` que incluya:

- Identificador de ejecución, inicio/fin, estado y parámetros no sensibles.
- Fuentes y checksums, versión del contrato y versión exacta del código ejecutado.
- Conteos de entrada, salida, rechazos y duplicados, con reglas de reconciliación.
- Resultados de controles y referencias locales de los rechazos, sin datos individuales en logs.
- Destino, particiones publicadas y comprobación posterior a la carga.

En cargas incrementales, avanzar el marcador de progreso solo tras confirmar la publicación.
Una repetición debe conservar el mismo resultado lógico, aunque cambien el ID y los tiempos
del registro de ejecución. Las agregaciones y joins deben explicar sus cambios de conteo;
no se presupone que filas de entrada y salida sean iguales.

## Uso del entorno actual

El código reutilizable de Extract vive en `src/factored_bank/extract/` y Transform/Load en
`src/factored_bank/etl/`. Los notebooks sirven para inspección y perfilado.
Los contratos deben validarse sobre tablas completas de manera adecuada al volumen; el ejemplo
Pydantic de `check-environment` solo demuestra validación de una fixture mínima.

`data/raw/` conserva entradas locales; `data/processed/` aloja resultados locales de desarrollo.
Los criterios de prueba están en `../evaluation/README.md`. La conexión de lectura S3 forma parte
de Extract; Compose ejecuta el scheduler integrado y mantiene separados los servicios.
