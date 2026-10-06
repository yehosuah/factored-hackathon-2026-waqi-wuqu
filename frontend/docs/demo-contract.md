# Contrato de integración del demo local

Fuente: contrato coordinado del proyecto, actualizado 4 de octubre de 2026,
y tipos del backend candidato `backend-demo-integration`. Base frontend `95a1a434`.
API y PostgreSQL se ejecutan por los responsables de backend/ETL; el frontend no migra
ni altera datos de esas implementaciones.

- Login Cliente: POST `/auth/login`; GET `/me`, `/me/cards`, movimientos paginados.
- Login Agente: POST `/agent/auth/login`; lista de casos y accept/resolve propios.
- Logout: POST `/auth/logout` o `/agent/auth/logout`, según principal.
- Preparar: POST `/me/cards/{product_id}/actions`, cuerpo action y parámetros del cargo
  solo para `unrecognized-charge`. `Idempotency-Key` obligatorio.
- Confirmación: GET `/me/action-confirmations/{id}`, POST `/{id}/confirm` o `/{id}/cancel`
  con cuerpo vacío. No hay bandera de confirmación controlada por frontend/modelo.
- Conversación: POST `/me/conversations` con language ES/PT e idempotencia;
  POST `/{id}/turns` con message/language/selected_product_id e idempotencia;
  GET paginado after/limit.
- Handoff: POST `/me/handoffs` con triage básico e idempotencia. Lista paginada y cancel;
  lista agente, accept y resolve. Los casos contienen contexto no confiable separado
  de evidencia backend. La asignación no es aceptación.

Las rutas se prefijan con `/api` en el navegador y Vite elimina ese prefijo. No se
introduce un identificador de cliente en cuerpos ni rutas: lo resuelve el backend
mediante bearer opaco. Token/contraseña nunca se persisten ni se incluyen en logs.

Los eventos se ordenan por sequence y se deduplican por event_id. Referencias de
confirmación solo se siguen desde eventos con trust=backend; GET confirma el estado
actual antes de habilitar el botón explícito. Prosa y aclaraciones trust=untrusted se
representan como texto escapado, sin HTML, enlaces ni controles ejecutables.

La integración usa modo anunciado por el adaptador. Solo `mode=stub` presenta atajos
`/cards`, `/pause <id>`, `/clarify`, `/handoff`, enviados como turnos al servidor.
`disabled` muestra falta de adaptador. En modo `injected`, el proveedor exacto
`intent-classifier` se etiqueta como clasificador local de intenciones en ES/PT.
El descriptor requiere provider/version no vacíos de hasta 100 caracteres, conforme
al contrato del backend. Otros proveedores conservan una etiqueta genérica.
Ningún modo crea evidencia desde texto.

El contrato de contexto acordado el 5 de octubre acepta `selected_product_id`
nullable y opcional. El frontend envía null cuando el cliente no elige una tarjeta
en el selector visible del chat; la selección de movimientos no se infiere. El ID
se envía separado del mensaje. El backend verifica pertenencia a la sesión/release,
lo incluye en el fingerprint de idempotencia y aclara referencias contradictorias.
La selección es contexto, nunca autoridad para ejecutar o confirmar.

El frontend captura message/language/selected_product_id junto a la clave original.
Repetir una solicitud incierta conserva ese cuerpo exacto. Logout/401 elimina
conversación, borradores y selección del chat.

Los eventos tool_result solo muestran recursos de lectura si trust=backend y
coinciden con los tipos de get_cards, get_card o get_movements. Las tarjetas se
presentan en el orden recibido, sin reordenar según el panel de cuenta. Esto permite
referencias ordinales al resultado autorizado. Los eventos históricos no habilitan
acciones: preparación, GET de estado actual, confirmación explícita y comprobante
siguen siendo pasos separados.

Recorrido de aceptación: ES/PT login/cards/movements, pausa por turno,
confirmación y comprobante/card refresh, aclaración, handoff, login agente/accept/resolve,
cliente refresh, logout/segundo cliente, y persistencia tras reinicio API/PostgreSQL.
Las pruebas unitarias usan transporte de prueba, no demuestran ese recorrido en PG.

Los recursos de tarjetas pueden incluir credit_limit decimal textual o null, y
last_updated ISO o null. Campos omitidos conservan compatibilidad con recursos
anteriores. Un límite omitido/null se presenta como no disponible en esos datos;
un valor conocido conserva importe y moneda, sin inferir elegibilidad. La fecha
mostrada corresponde a la actualización del producto, no al corte de todo el dataset.

Handoff puede incluir conversation_snapshot de handoff-conversation-v1 o null;
casos históricos pueden omitirlo. Hasta 20 eventos ordenados, extractos de 200
caracteres y consultas con hasta 10 filas. El frontend valida esos límites y separa
texto proporcionado, consultas verificadas, comandos pendientes/cancelados,
comprobantes ejecutados e intentos fallidos/desconocidos. Es una instantánea al crear
el caso: no prueba el estado actual ni su resolución. No se descarga historia de
otros clientes ni se vuelve a enviar información financiera al clasificador.
