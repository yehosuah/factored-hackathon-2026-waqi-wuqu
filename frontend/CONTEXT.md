# Glosario del dominio

- **Cliente (`customer`)**: titular bancario identificado por `customer_id` en el dataset.
  Un identificador de cliente o documento por sí solo no prueba identidad.
- **Producto (`product`)**: cuenta, tarjeta, préstamo, inversión o seguro asociado
  a un cliente, identificado por `product_id`.
- **Transacción (`transaction`)**: movimiento financiero registrado con
  `transaction_id`, importe, moneda, tipo y estado.
- **Interacción (`interaction`)**: contacto de servicio registrado con
  `interaction_id`, canal, motivo y resultados de atención.
- **Transcripción (`transcript`)**: texto de una llamada asociado a una interacción.
- **Agente humano (`service_agent`)**: persona que atiende al cliente; se distingue
  del agente de IA que participa en el flujo conversacional.
- **Reclamo (`complaint`)**: caso de queja, reclamo, solicitud o sugerencia registrado
  en la tabla `complaints`.
- **Flujo de atención (`workflow`)**: secuencia delimitada que entiende una solicitud,
  decide, actúa, verifica el resultado y escala cuando corresponde.
- **Resolución automatizada segura**: caso elegible resuelto correctamente y de acuerdo
  con la política, sin intervención humana.
- **Contención (`containment`)**: cierre sin transferencia; por sí solo no demuestra resolución.
- **Escalamiento (`escalation`)**: transferencia a una persona cuando la atención lo requiere.
- **Traspaso (`handoff`)**: contexto estructurado entregado a una persona, con solicitud,
  hechos verificados, acciones, evidencia y preguntas pendientes.
- **Resultado inseguro (`unsafe outcome`)**: divulgación o acción no autorizada,
  o resultado materialmente incorrecto.
- **Baseline**: sistema de referencia contra el cual se compara la propuesta usando
  la misma carga de evaluación reservada.
- **Evaluación reservada (`held-out evaluation`)**: casos separados del desarrollo
  y del ajuste para medir el comportamiento final.
- **Fixture**: datos de prueba controlados y etiquetados como tales.
- **FCR (`first call resolution`)**: resolución en el primer contacto, representada
  por `was_resolved` en las interacciones del dataset.
- **CSAT**: puntuación de satisfacción del cliente; en el diccionario, de 1 a 5.
- **NPS**: indicador de recomendación basado en respuestas de 0 a 10 y categorías
  de promotor, pasivo y detractor.
- **Moneda (`currency`)**: código monetario; el dataset describe MXN, COP, ARS y USD.

Fuentes: diccionario del dataset y problem statement, referenciados en `docs/reto.md`.
