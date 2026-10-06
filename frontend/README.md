# FactoredAI_FRT

Demo local de atención de tarjetas en español y portugués. React 19, TypeScript y
Vite. El backend aplica identidad, aislamiento por cliente y confirmación explícita;
la interfaz muestra sus estados y evidencia. Datos sintéticos y acciones simuladas.
El modo anunciado por el backend distingue el stub de ingeniería de un adaptador
de conversación. El proveedor `intent-classifier` se muestra como clasificador local
de intenciones; no es un LLM y su texto no verifica acciones.

## Ejecutar

Desde esta carpeta, con Node.js 24 y npm:

```sh
npm ci
FACTORED_API_TARGET=http://127.0.0.1:8000 npm run dev -- --port 5173 --strictPort
```

Abre `http://127.0.0.1:5173/`. `FACTORED_API_TARGET` es una variable del servidor
Vite, nunca una variable `VITE_*` ni un secreto. Debe apuntar al backend sintético
local. El proxy de desarrollo envía `/api/*` a ese backend y elimina `/api`.
No agregues CORS abierto ni expongas el servidor fuera de loopback.

El backend y PostgreSQL deben estar listos y las cuentas sintéticas provisionadas
por sus responsables. Usa las credenciales de prueba que esos responsables entreguen
por su canal privado; este repositorio no incluye contraseñas ni datos de clientes.
Sin backend se pueden ver los portales de entrada, pero el login devolverá un error.

```sh
npm test       # pruebas de transporte, estado, confirmación y aislamiento
npm run check  # ESLint, TypeScript y build Vite
```

`npm run preview` sirve el build estático para revisión visual; no configura el proxy
API. Para servir el build con proxy same-origin y headers de seguridad utiliza
[docs/production-serving.md](docs/production-serving.md). No se ha desplegado.

## Recorrido del demo

El header compartido separa las vistas de cliente: Home (`/#home`) muestra la
vista general y los casos; Tarjetas (`/#cards`) contiene productos, movimientos y
confirmaciones; Asistencia (`/#chat`) contiene el chat. Las rutas anteriores
`/#main` y `/#cards-title` conservan acceso a Home y Tarjetas respectivamente.

Asistencia abre la página dedicada `/#chat`, con nueva conversación, mensajes y
selección del historial de la sesión autenticada. El historial visible se mantiene
solo en memoria y se limpia al salir o recargar; no hay todavía un endpoint para
listar conversaciones de sesiones anteriores. Seleccionar un chat vuelve a consultar
su contenido autorizado al backend. Los casos creados desde esa conversación muestran
su estado en el mismo espacio; no se simulan mensajes de empleados ni chat humano en vivo.

1. Entra como Cliente. Consulta tarjetas y movimientos históricos.
2. Pausa una tarjeta con el botón o inicia una conversación y envía
   `/pause <product_id>` si el backend anuncia `adapter.mode=stub`. Con el clasificador
   local, escribe la solicitud en ES/PT y elige opcionalmente la tarjeta en el chat.
   El ID viaja separado del mensaje; una consulta de tarjetas conserva su orden
   para que puedas referirte a una de ellas.
3. La acción queda pendiente. Solo **Confirmar esta acción simulada** llama a
   `/me/action-confirmations/{id}/confirm`; Cancelar guarda la cancelación.
4. Un comprobante solo se muestra como verificado si coincide con el comando y
   contiene estado, procedencia, versión e ID de acción válidos. La tarjeta se actualiza.
5. En el stub usa `/clarify` y `/handoff`. También puedes solicitar atención humana
   con un resumen explícito. El texto de conversación se muestra como no verificado.
6. Cierra la sesión. Entra en Agente humano con la cuenta independiente. Acepta el
   caso asignado y luego resuélvelo. Asignado, aceptado y resuelto son estados distintos.
7. Cierra la sesión del agente y vuelve al cliente para consultar el estado persistido.

Los accesos de Cliente y Agente usan rutas y bearer diferentes. El token permanece en
memoria y no se guarda en cookies, storage ni URLs. Logout y 401 borran todos los
recursos y borradores del cliente. La recarga del navegador requiere volver a entrar;
la persistencia de conversaciones y acciones pertenece al backend.

Las operaciones con efectos guardan una clave de idempotencia por solicitud. Una
respuesta perdida o una espera cancelada bloquea comandos nuevos hasta repetir la
**misma** solicitud con su clave original o cerrar sesión. Detener espera no implica
cancelar un comando guardado; el botón Cancelar de la confirmación es una operación
separada. Los errores persistidos en un turno HTTP 200 permanecen visibles como errores.

## Contrato y límites

Consulta [docs/demo-contract.md](docs/demo-contract.md) y [docs/reto.md](docs/reto.md).
El backend candidato implementa `conversation-adapter-v1`. El equipo ML es responsable
del proveedor real y de su evaluación. Este frontend no interpreta comandos por su
cuenta, no confirma desde prosa y no afirma reembolsos, emisión ni cambios en un banco.

Los saldos y movimientos de la fuente son históricos; los cambios de estado pertenecen
al simulador. Los agentes se asignan desde una instantánea sintética, sin afirmar
presencia en vivo. Las acciones reemplazo y cargo no reconocido registran solicitudes
según la evidencia recibida, no el resultado final de una revisión humana.

## Recorridos guiados y aceptación

En Asistencia, abre «¿Qué necesitas hacer?» para elegir tarjeta y motivo. La selección
se envía como turno y requiere la confirmación posterior del backend. El modo stub solo
admite pausa; pérdida/robo y cargo conversacional requieren el adaptador real.

Desde un movimiento puedes abrir el chat con su contexto o preparar el reporte directo.
Tras confirmar un cargo y recibir su comprobante, «Continuar con atención humana» crea
un caso con referencias al movimiento y solicitud. Ese endpoint aún no vincula formalmente
el caso a una conversación; la interfaz distingue el contexto aportado de la evidencia.

Consulta [la aceptación del frontend](docs/frontend-acceptance.md) para los resultados
verificados y las dependencias de backend/ML que siguen abiertas.
