# Cierre de frontend — 4 de octubre de 2026

## Cambios implementados

- P02: procedencia, actualización de la fuente y versión de datos junto a la tarjeta;
  fecha del movimiento y fecha de proceso separadas. `last_updated` no se presenta
  como fecha de corte global. Importes nulos se muestran como no disponibles.
- P06: selección explícita de tarjeta y pausa temporal/pérdida o robo en el chat.
  El frontend envía la elección como turno; nunca confirma una acción a partir del texto.
  Cambiar idioma mantiene la conversación y no altera comandos ya preparados.
- P07: aviso de bloqueo no reversible tanto al confirmar como en la tarjeta bloqueada.
- P08: movimiento seleccionable como contexto del chat; cargo confirmado con comprobante
  permite crear un caso con producto, movimiento, fecha de proceso, solicitud y pregunta
  pendiente. Reintentos conservan payload y clave. No se afirma reembolso.
- P12: traducciones ES/PT de vocabulario conocido, importes y fechas; historial modal
  con foco contenido y retorno al disparador; respeto de movimiento reducido; controles móviles.

## Validación realizada

- 37 pruebas de estado, transporte y contratos: aprobadas. Cinco pruebas nuevas cubren
  dinero nullable, contexto/idioma, límites del stub, identidad compuesta del movimiento
  y creación de caso desde comprobante con respuesta perdida.
- ESLint, TypeScript y build Vite: aprobados ejecutando sus herramientas directamente.
  El comando agregado npm no mostró sus pasos internos en este host, por lo que no se
  usó su código de salida como única evidencia.
- Cliente frontend contra API local y PostgreSQL existentes: 12 comprobaciones aprobadas.
  Login, contratos de tarjetas/movimientos, aclaración ES/PT en una conversación,
  preparación/cancelación de pausa sin cambio, pausa y comprobante, repetición con el
  mismo comprobante, reactivación, cargo registrado, caso con contexto y cancelación
  del caso de verificación. Tarjeta restaurada a su estado ACTIVE inicial. Se conservan
  los registros de auditoría de esas acciones simuladas.
- Navegador con transporte de prueba aislado: reporte → confirmación → comprobante → caso
  con referencias; pausa guiada PT y comprobante; historial con Escape/foco de retorno.
  Revisión de escritorio y móvil 390 × 844: sin desbordamiento horizontal en el chat.
  Estas pruebas visuales no equivalen a aceptación del proveedor ML real.

## Dependencias abiertas fuera del frontend

1. El stub solo admite `/cards`, `/pause`, `/clarify` y `/handoff`. No resuelve pérdida/robo
   ni cargos conversacionales. Se informa el límite y se ofrecen los controles de tarjetas;
   el frontend ya envía los turnos contextualizados al adaptador injected cuando exista.
2. POST `/me/handoffs` acepta contexto y producto, pero no `conversation_id`. El caso directo
   puede incluir otras acciones de la tarjeta. Las referencias del frontend son contexto
   no verificado; el backend debe implementar el vínculo formal y evidencia limitada a
   la conversación para completar P08 del plan. No se inventó un campo incompatible.
3. Falta endpoint de listado de conversaciones para recuperar el historial tras recarga.
   Tokens e historial siguen en memoria y se eliminan al cerrar sesión.
4. Falta fecha de corte global autoritativa en la API. Se distingue de `last_updated` y
   de `process_date`; ninguna fecha se fabrica.
5. Aceptación completa con ML real, reinicio del stack compartido y despliegue TLS
   corresponde a integración. No se certifica P11/P14 ni se reiniciaron servicios.

Solo se modificó el repositorio frontend. La publicación revisada posterior se documenta abajo; no hubo despliegue.

## Integración reconciliada para la entrega del 5 de octubre

Se conservaron los commits originales del autor y los cambios de PR2 mediante merges,
incluyendo main `da12a3b`. El head reconciliado pasa 62 pruebas sin skips,
ESLint/TypeScript/build y cinco comprobaciones de configuración/Nginx real.

Navegador real contra PostgreSQL/API sintéticos coordinados: cargo de movimiento
`DEMO-TX-001` → preparación pendiente → revisión fresca → confirmación explícita →
comprobante tipado → caso cuya evidencia contiene el mismo action/request/product.
El contexto devuelto también debe coincidir con el enviado. Esto verifica la asociación
con el comprobante; no convierte el contexto en evidencia ni limita todo el caso a
una conversación. Se probó ES/PT, sin afirmar reembolso.

Tres casos creados por esta aceptación fueron aceptados y resueltos por el agente
sintético separado, con respuestas 200 y estados backend accepted/resolved. Logout
limpió tarjetas, casos y chat; no se almacenan sesiones en local/sessionStorage/cookies.
La prueba de reintento 503→422 conserva borrador/payload/key; un turno realmente
persistido cuya respuesta se ocultó se repite con el mismo turn/event IDs y se limpia
solo tras acuse. Los fallos se inyectaron en el navegador aislado, nunca en el stack.

Regresiones: skip por teclado conserva la página y enfoca main; glosario PT también
se usa en etiquetas de confirmación; los eventos no confiables no adjuntan controles
para una confirmación de otra conversación. Esta última prueba usa una proyección
rotulada de respuestas del navegador y cancela explícitamente el comando sintético
pendiente. El documento móvil mide 390px en viewport390, con scroll interno en tabla.

El adaptador observado se identifica como clasificador local de intenciones,
`intent-tfidf-lr-v1`; no certifica un proveedor ML generativo real. La aceptación
anterior del autor se conserva arriba como evidencia de su propio checkout. El
frontend se publica en PRs revisados; no se despliega ni cambia la visibilidad.

Regresiones finales de PR3: se proyectó en respuestas aisladas de navegador un
handoff_id real de otro caso sobre un evento no confiable. El chat mostró cero
transferencias falsas y el backend no se modificó. En conversación activa a 390×844,
ES/PT mantienen visibles tanto el aviso de datos sintéticos/confirmación como la
etiqueta del clasificador, sin desbordamiento horizontal. Se conservan 62 tests y
cinco checks de configuración/Nginx real aprobados; capturas usan solo datos sintéticos.

Último ajuste de revisión: comprobantes históricos sin identidad completa del cargo
siguen visibles, pero no ofrecen un botón activo que no pueda crear el caso. El
control deshabilitado explica ES/PT que faltan movimiento/fecha; targets vacíos o
solo whitespace tampoco publican casos. 63 tests completos aprobados. La regresión
rotulada de navegador usó un comprobante real proyectado sin campos opcionales,
mostró control deshabilitado/explicación ES/PT, registró cero POSTs de casos y logout200.

Revisión adicional: el selector permite volver a consulta sin tarjeta y el siguiente
turno publica selected_product_id:null. Un cargo solo puede continuar con identidad
de movimiento y fecha YYYY-MM-DD exacta/calendario válido; fechas imposibles, texto
y timestamps no crean casos. IDs de handoff vacíos/whitespace se rechazan antes de
vincular recibos, mostrando error y conservando replay de la solicitud original.
65 tests completos y lint/typecheck/build aprobados.
