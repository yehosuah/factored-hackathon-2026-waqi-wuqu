# Servir el build

La aplicación utiliza `/api/` en el mismo origen. `vite dev` y `vite preview` no son
el servidor de producción. `deploy/render_nginx.py` genera una configuración de
Nginx para servir `dist/` y enviar `/api/*` a un origen fijo del backend, eliminando
solo el prefijo. Requiere Python 3.9+, Nginx y un build con Node 24.

## Prueba local

Con el backend sintético listo y un puerto frontend libre:

```sh
npm ci
npm test
npm run check
python3 deploy/render_nginx.py \
  --prefix "$PWD/tmp/nginx" \
  --api-origin http://127.0.0.1:8000 \
  --public-origin http://127.0.0.1:8080 --port 8080 --local
nginx -e stderr -p "$PWD/tmp/nginx" -c "$PWD/tmp/nginx/nginx.conf" -t
nginx -e stderr -p "$PWD/tmp/nginx" -c "$PWD/tmp/nginx/nginx.conf" -g 'daemon off;'
```

Abre `http://127.0.0.1:8080/`. El proceso corre sin privilegios, solo en loopback.
Detén ese proceso con Ctrl+C. No necesita contraseñas en el archivo de configuración.
Para verificar el proxy con un upstream sintético aislado:

```sh
FACTORED_SERVING_INTEGRATION=1 python3 -m unittest discover -s deploy -p 'test_*.py' -v
```

## Contrato con el host

Para un host real, `--public-origin` exige HTTPS. Termina TLS en el edge del host y
redirige HTTP a HTTPS allí. Configura HSTS en ese edge después de validar el dominio
y el certificado. El servicio HTTP de Nginx debe ser privado; si el host requiere
`--bind 0.0.0.0`, limita su acceso por red al edge. El edge debe conservar el Host
público configurado; otros hosts reciben 421. No se realizó un despliegue público.

`--api-origin` debe ser un origen fijo de la red privada autorizada y usar HTTPS.
Proporciona `--ca-bundle /ruta/ca-certificates.crt`; se verifica el certificado y
el nombre del upstream. HTTP solo se acepta con `--local` y un origen loopback
(`localhost`, `127.0.0.1` o `::1`). Las direcciones de red privada y
`host.docker.internal` también requieren HTTPS: no se permite una excepción HTTP
para un salto entre contenedores o hacia el host Docker. Un origen con usuario, contraseña, ruta,
query o caracteres de control es rechazado. No derives el upstream del navegador.

El proxy conserva Authorization, Idempotency-Key y el cuerpo. Sustituye los headers
forwarded del cliente con el esquema público fijo y la dirección del salto recibido.
El backend sigue aplicando sesión, permisos, aislamiento y límites por principal;
un edge adicional necesita su propia política de confianza de IP. El frontend no
introduce secretos, cookies de sesión ni almacenamiento persistente del bearer.

No hay reintentos automáticos de POST, caché de API ni buffering de sus respuestas.
Una caída de API devuelve un error HTTP, nunca el HTML de la aplicación. HTML y
errores llevan no-store; los assets con hash exitosos llevan caché immutable. El
límite del proxy es 128 KiB y debe coincidir con el backend. El access log está
deshabilitado y el error log no registra headers ni cuerpos; cualquier observabilidad
adicional debe redactar tokens y datos de clientes. Nginx puede escribir cuerpos
temporales acotados: usa un volumen temporal privado y limpia al terminar el servicio.

CSP permite scripts, estilos y conexiones del mismo origen, sin inline ni eval;
también se envían nosniff, no-referrer, frame denial, COOP y una política que desactiva
cámara, micrófono y geolocalización. Las pruebas locales verifican el contrato HTTP;
TLS público, backups, rotación de credenciales, alertas y pruebas de carga dependen
del entorno elegido y no quedan demostrados por un build.

La semántica de eliminación del prefijo y de los reintentos sigue la
[documentación de proxy de Nginx](https://nginx.org/en/docs/http/ngx_http_proxy_module.html).
La herencia de los headers y `always` se documenta en
[Nginx headers](https://nginx.org/en/docs/http/ngx_http_headers_module.html).
La política se apoya en la [guía CSP de MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP).
