# Glosario del dominio

Fuentes: diccionario LATAM Bank v1.0.0 y enunciado del reto en `GeneralInfo/`.
Las referencias por página se encuentran en `docs/hackathon-brief.md`.

| Término | Definición |
| --- | --- |
| Cliente (`customer`) | Persona representada en `customers`, identificada por `customer_id`. El identificador no constituye autenticación. |
| Producto (`product`) | Cuenta, tarjeta, préstamo u otro producto de un cliente en `products`, identificado por `product_id`. |
| Transacción (`transaction`) | Movimiento registrado en `transactions`, con importe, moneda, estado y relaciones con cliente y producto. |
| Interacción (`interaction`) | Contacto de servicio en `call_center_interactions`, identificado por `interaction_id`. |
| Motivo de contacto (`contact_reason`) | Razón principal registrada para una interacción. |
| Transcripción (`transcript`) | Texto de una llamada en `call_transcripts`, relacionado con una interacción. |
| Agente de servicio (`service_agent`) | Representante humano registrado en `service_agents`; no es un agente de IA. |
| Reclamo (`complaint`) | Caso de atención en `complaints`; puede ser queja, reclamo, solicitud o sugerencia. |
| Resolución en primer contacto (FCR) | Resolución en el primer contacto; el diccionario describe `was_resolved` con este significado. |
| CSAT | Medida de satisfacción; `main_score` usa escala de 1 a 5 para encuestas CSAT. |
| NPS | Medida de recomendación; `main_score` usa escala de 0 a 10 para encuestas NPS. |
| Resolución automatizada segura | Caso elegible que alcanza un resultado correcto y conforme a política sin intervención humana. |
| Contención | Caso que termina sin transferencia; no prueba por sí sola que se resolvió. |
| Transferencia humana (`handoff`) | Entrega estructurada de solicitud, hechos verificados, acciones, evidencia y preguntas pendientes. |
| Resultado inseguro | Divulgación o acción no autorizada, o resultado materialmente incorrecto. |
| Conjunto reservado (`held-out`) | Casos separados de desarrollo y ajuste para evaluar sin filtración de información. |
| Fixture | Datos de prueba controlados; las fixtures del equipo se identifican por separado de los datos del organizador. |
| Fecha de proceso (`process_date`) | Fecha usada como clave de partición en tablas de hechos; no equivale necesariamente a la fecha del evento. |
| Entrega aceptada (`accepted release`) | Versión completa e inmutable publicada por el ETL; el puntero PostgreSQL indica la versión disponible para consumidores. |
| Cuarentena (`quarantine`) | Filas excluidas de la entrega aceptada con originales, trazabilidad y causas conservadas; no se eliminan del histórico raw. |
| Estado del simulador (`simulator state`) | Estado persistente de una tarjeta para herramientas de prueba; separado del estado histórico del organizador y conservado tras refrescos ETL. |
