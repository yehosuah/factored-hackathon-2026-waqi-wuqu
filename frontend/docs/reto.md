# Contexto del reto y límites de esta base

## Fuentes

Documentos locales revisados, conservados sin modificaciones:

- [Problem statement](../GeneralInfo/Factored%20AI%20%26%20Data%20Hackathon%202026%20%281%29.pdf),
  pp. 2–6: alcance, comportamiento, evaluación y límites de ejecución.
- [Kickoff](../GeneralInfo/Datathon_2026_Kickoff%20%281%29.pdf),
  pp. 10–15 y 18–20: requisitos, entregables y evaluación.
- [Dataset summary](../GeneralInfo/LATAM_Bank_Dataset_Summary%20%281%29.pdf),
  pp. 2–5: cobertura, tablas y calidad declarada.
- [Data dictionary](../GeneralInfo/LATAM_Bank_Complete_Data_Dictionary%20%281%29.pdf),
  pp. 2–15 y 17: campos, restricciones y relaciones.

## Objetivo del producto

Construir un prototipo funcional de atención bancaria con IA para un flujo concreto,
con evidencia de preparación para operación y una explicación de lo que falta.
El reto no exige operar un banco real. Los ejemplos son consultas de cuenta/pagos,
soporte de tarjetas, recepción de disputas e información/elegibilidad de crédito.
El demo actual eligió atención de tarjetas con datos sintéticos; la documentación
y la evaluación deben distinguir este alcance de las cifras generales del dataset.

Debe haber una resolución normal, una solicitud ambigua o no soportada, y un caso
de intervención humana. La solución debe mantener contexto, aclarar, consultar
fuentes autorizadas y confirmar los resultados de las acciones antes de reportarlos.

## Requisitos que afectan al frontend

- Interacciones en español y portugués. Cambiar los textos de la pantalla inicial
  no demuestra capacidad conversacional multilingüe.
- Representar estados de carga, error, sesión expirada, aclaración, confirmación,
  acción verificada y escalamiento cuando se implemente el flujo.
- Mostrar evidencia autorizada y resultados verificados recibidos del servicio.
- Distinguir una acción solicitada de una acción completada.
- Permitir traspaso estructurado: solicitud, hechos, acciones, evidencia y dudas abiertas.
- Mantener secretos e información restringida fuera de los archivos públicos y
  del bundle del navegador. Las variables `VITE_*` son públicas.
- Aplicar identidad, acceso por cliente y permisos en el servicio/backend.
  Un número de documento o cliente no basta como autenticación.

## Datos disponibles y limitaciones

Este repositorio de frontend no distribuye el dataset ni credenciales. El runtime
local de backend/ETL publica un fixture sintético independiente. Las cifras siguientes
son declaraciones de los documentos, no resultados de una auditoría de ese fixture:

- Dataset sintético v1.0.0, aproximadamente 19 millones de filas y 13 tablas.
- México, Colombia y Argentina; periodo 2023-06-17 a 2026-06-17.
- Monedas MXN, COP, ARS y USD; textos en español con variaciones regionales.
- Se describen duplicados (~2%), nulos (~5% en campos anulables), llegadas tardías,
  evolución de esquema y algunos registros huérfanos.

Tablas: `customers`, `products`, `branches`, `service_agents`, `marketing_campaigns`,
`transactions`, `call_center_interactions`, `call_transcripts`, `satisfaction_surveys`,
`digital_events`, `complaints`, `campaign_sends`, `daily_exchange_rates`.

El portugués es un requisito del producto, pero no una cobertura declarada del dataset.
Se necesitarán casos de evaluación en portugués con procedencia explícita.
No se deben inventar reglas de elegibilidad ni inferir políticas bancarias a partir de
los nombres de campos. El contrato implementado se documenta en [demo-contract.md](demo-contract.md).

## Evaluación y entrega final del reto

Comparar baseline y propuesta sobre los mismos casos reservados, con contratos,
calidad, trazabilidad y prevención de fuga de información. Evaluar al menos un
componente aprendido. Incluir fallos, inyección de instrucciones, datos faltantes,
acceso no autorizado, sesiones vencidas y fallos de herramientas.

Reportar resolución automatizada segura, cobertura de intentos de automatización,
resultados inseguros, calidad del traspaso, latencia p50/p95 y costo por intento y
por resolución segura. Desglosar idiomas, tamaños de muestra y limitaciones.
Separar mediciones offline, simulaciones y ahorros proyectados.

El kickoff solicita repositorio público con nombre
`factored-hackathon-2026-[nombre-del-equipo]`, enlace desplegado, presentación de
4–6 slides y video corto. El nombre actual del repo todavía no sigue ese formato.
Los entregables de publicación, presentación y video requieren evidencia separada;
este frontend local no acredita que ya se hayan entregado.

## Alcance implementado ahora

El frontend implementa login independiente de cliente y agente, tarjetas y movimientos
históricos, preparación de acciones, revisión del estado actual, confirmación explícita,
comprobante tipado y actualización de tarjeta. El traspaso muestra contexto de
conversación separado de evidencia backend; los agentes aceptan y resuelven sus casos.
Hay estados de carga, error, sesión vencida, espera cancelada y repetición exacta de
solicitudes inciertas. No se persisten tokens en cookies ni storage del navegador.

La conversación usa el modo anunciado por el backend. Solo el stub presenta comandos
de ingeniería. El proveedor intent-classifier es un clasificador aprendido local con
plantillas ES/PT, sin LLM. La selección de tarjeta se envía separada del mensaje; el
backend conserva identidad, pertenencia, elegibilidad y ejecución. Ningún texto del
adaptador confirma una acción por sí mismo.

La validación distingue pruebas unitarias/transporte, browser contra backend sintético
y evaluación del modelo. Una prueba de interfaz no sustituye evidencia de PostgreSQL,
reinicios ni resultados de evaluación reservada. Consulte [README.md](../README.md)
y [demo-contract.md](demo-contract.md) para instalación, contrato y límites.

## Aceptación integrada pendiente

El candidato del clasificador y sus mejoras de interfaz deben comprobarse juntos sobre
el runtime congelado por backend/ETL. El recorrido incluye ES/PT, lectura de saldo y
límite, selección/ambigüedad/conflictos de tarjeta, confirmación/cancelación, comprobantes,
aislamiento entre clientes y traspaso a un agente independiente. Las revisiones deben
corresponder al mismo head final. No hay despliegue ni operaciones bancarias reales.
