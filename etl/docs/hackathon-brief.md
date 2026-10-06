# Requisitos y fuentes del hackathon

Esta síntesis procede de los cuatro PDF locales. Es contexto del reto, no una afirmación
de funcionalidades implementadas. El ambiente inicial solo verifica herramientas locales.

Este documento conserva los requisitos del proyecto completo. Este repositorio implementará
su ETL: contratos, calidad, preparación reproducible, linaje y entrega de datos.
Las obligaciones del servicio conversacional y la evaluación de modelos corresponden a los
consumidores. El alcance de este repositorio está en [etl.md](etl.md).

## Objetivo

Construir un prototipo de atención bancaria centrado en un flujo coherente, justificado por datos.
Debe entender, decidir, actuar, verificar y escalar. Los ejemplos incluyen consultas de cuenta/pagos,
soporte de tarjetas, recepción de disputas e información/elegibilidad crediticia.
El flujo seleccionado durante el diseño es soporte de tarjetas de débito y crédito.
Su alcance, la extracción de nueve tablas y las decisiones todavía pendientes se encuentran en
la [alcance de datos](design/card-support-data.md). El flujo aún no está implementado.

## Requisitos que deben guiar el desarrollo posterior

| Requisito | Evidencia futura | Fuente |
| --- | --- | --- |
| Justificar el flujo con datos | Análisis de motivos de contacto, demanda y calidad | Enunciado, p. 3 |
| Español y portugués | Casos y resultados por idioma; limitaciones declaradas | Enunciado, p. 3 |
| Resolución normal, ambigüedad y transferencia humana | Demostración de las tres rutas | Enunciado, p. 3 |
| Contexto y respuestas fundamentadas | Fuentes permitidas y resultados de herramientas verificados | Enunciado, p. 3 |
| Permisos fuera del modelo | Autenticación de prueba y aislamiento por cliente | Enunciado, pp. 3 y 5 |
| Preparación reproducible | Contratos, calidad, linaje y política de actualización | Enunciado, pp. 3-4 |
| Componente aprendido frente a baseline | Mismos casos reservados, etiquetas válidas y prevención de leakage | Enunciado, pp. 3-5 |
| Manejo de fallos | Casos de datos faltantes, sesión expirada, acceso indebido, inyección y fallos de herramientas | Enunciado, pp. 3-4 |
| Métricas explícitas | Resolución segura, contención, escalamiento, resultados inseguros, latencia p50/p95 y coste | Enunciado, pp. 5-6 |
| Ruta a operación | Trazas, reintentos acotados, fallback, monitoreo y limitaciones | Enunciado, p. 4 |

Un prototipo con herramientas simuladas es aceptable si se documentan sus contratos y limitaciones.
No se autoriza movimiento real de dinero ni decisiones reales de crédito. Un documento nacional
o número de cliente, por sí solo, no prueba identidad. No se deben enviar registros privados,
credenciales o datos restringidos a repositorios públicos ni modelos externos (enunciado, p. 5).

## Descripción del dataset y alcance adquirido

Extract adquirió las nueve tablas acordadas; su [evidencia medida](design/extract-card-support/verification-v1.md)
se registra por separado. Los volúmenes y trece tablas descritos a continuación pertenecen al
dataset completo del proveedor, no al alcance adquirido.

El dataset v1.0.0 es sintético, de México, Colombia y Argentina, con fechas del
2023-06-17 al 2026-06-17 y monedas MXN, COP, ARS y USD. Declara aproximadamente 19 millones
de registros y 13 tablas. El volumen es documental, no una medición local.

| Tipo | Tablas |
| --- | --- |
| Dimensiones | `customers`, `products`, `branches`, `service_agents`, `marketing_campaigns` |
| Hechos | `transactions`, `call_center_interactions`, `call_transcripts`, `satisfaction_surveys`, `digital_events`, `complaints`, `campaign_sends` |
| Referencia | `daily_exchange_rates` |

Las fuentes describen aproximadamente 2% de duplicados, 5% de nulos en campos anulables,
llegadas tardías, evolución de esquema y una pequeña proporción de referencias huérfanas.
Estos porcentajes deben verificarse sobre los archivos recibidos.

La documentación indica que todos los textos del dataset están en español. El requisito de
portugués del reto necesitará evidencia adicional, identificada por origen y método de validación.
El resumen afirma conversión a USD, pero el diccionario permite `amount_usd` nulo:
el contrato real deberá comprobarse antes de asumir cobertura completa.

## Entrega final del evento

El kickoff (p. 18) solicita repositorio público con nombre
`factored-hackathon-2026-[nombre-del-equipo]`, enlace al despliegue, presentación de 4-6 slides
y video breve obligatorio. Esto describe una entrega futura; no se publica nada con este setup.

## Fuentes locales

Los PDF originales son referencias locales en `GeneralInfo/`, fuera de Git. Las citas
conservan sus nombres y páginas para auditar esta síntesis cuando estén disponibles.

- [Enunciado](../GeneralInfo/Factored%20AI%20%26%20Data%20Hackathon%202026%20%281%29.pdf), pp. 2-6.
- [Kickoff](../GeneralInfo/Datathon_2026_Kickoff%20%281%29.pdf), pp. 10-15 y 18-20.
- [Resumen del dataset](../GeneralInfo/LATAM_Bank_Dataset_Summary%20%281%29.pdf), pp. 2-5.
- [Diccionario completo](../GeneralInfo/LATAM_Bank_Complete_Data_Dictionary%20%281%29.pdf), pp. 2-15 y 17.
