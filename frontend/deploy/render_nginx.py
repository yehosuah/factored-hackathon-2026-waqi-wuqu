"""Render a fixed-origin, non-root Nginx server for the built demo. No secrets."""
from __future__ import annotations
import argparse
import ipaddress
import re
from pathlib import Path
from urllib.parse import urlsplit


def origin(value: str, *, local: bool = False, upstream: bool = False) -> tuple[str, str]:
    if any(ord(c) <= 32 or ord(c) == 127 for c in value):
        raise ValueError("Origin cannot contain whitespace or control characters")
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment
            or not re.fullmatch(r"[A-Za-z0-9.:[\]-]+", parsed.netloc)):
        raise ValueError("Expected an HTTP(S) origin without credentials, path or query")
    port = parsed.port  # Also rejects invalid/out-of-range ports.
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Invalid origin port")
    if parsed.scheme != "https":
        try:
            loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            loopback = parsed.hostname == "localhost"
        if not local or not loopback:
            role = "API" if upstream else "Public"
            raise ValueError(f"{role} origin requires HTTPS; local HTTP requires loopback")
    return f"{parsed.scheme}://{parsed.netloc}", parsed.hostname


def quoted_path(path: Path) -> str:
    value = str(path.resolve())
    if any(c in value for c in ('"', "\\", "$", "\n", "\r", "\x00")):
        raise ValueError("Unsafe Nginx path")
    return '"' + value + '"'


def render(dist: Path, prefix: Path, api_origin: str, public_origin: str,
           port: int, *, local: bool = False, bind: str = "127.0.0.1",
           ca_bundle: Path | None = None) -> str:
    upstream, _ = origin(api_origin, local=local, upstream=True)
    public, hostname = origin(public_origin, local=local)
    address = ipaddress.ip_address(bind)
    if urlsplit(public).scheme == "http" and not address.is_loopback:
        raise ValueError("HTTP public origin requires a loopback listen address")
    if not 1024 <= port <= 65535:
        raise ValueError("Use a non-root listen port")
    if not (dist / "index.html").is_file():
        raise ValueError("Build dist/index.html first")
    root = quoted_path(dist)
    pid, body, proxy = (quoted_path(prefix / name) for name in ("nginx.pid", "body", "proxy"))
    listen = f"[{bind}]:{port}" if ":" in bind else f"{bind}:{port}"
    # This HTTP service sits behind a TLS edge in production. The fixed public
    # scheme replaces incoming forwarded metadata; the upstream is never client-selected.
    scheme = urlsplit(public).scheme
    tls = ""
    if urlsplit(upstream).scheme == "https":
        if ca_bundle is None or not ca_bundle.is_file():
            raise ValueError("HTTPS upstream requires an existing CA bundle")
        tls = f"proxy_ssl_server_name on;\n      proxy_ssl_verify on;\n      proxy_ssl_trusted_certificate {quoted_path(ca_bundle)};"
    return f'''pid {pid};
error_log stderr warn;
worker_processes auto;
events {{ worker_connections 1024; }}
http {{
  types {{ text/html html; text/css css; application/javascript js; application/json json; image/svg+xml svg; image/png png; image/x-icon ico; font/woff2 woff2; }}
  default_type application/octet-stream;
  server_tokens off;
  access_log off;
  client_body_temp_path {body};
  proxy_temp_path {proxy};
  map "$status:$uri" $response_cache {{ default no-store; ~^(200|304):/assets/ "public, max-age=31536000, immutable"; }}
  client_max_body_size 128k;
  client_body_timeout 15s;
  send_timeout 30s;
  keepalive_timeout 30s;
  add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'" always;
  add_header X-Content-Type-Options nosniff always;
  add_header X-Frame-Options DENY always;
  add_header Referrer-Policy no-referrer always;
  add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
  add_header Cross-Origin-Opener-Policy same-origin always;
  add_header Cache-Control $response_cache always;
  server {{
    listen {listen} default_server;
    server_name _;
    return 421;
  }}
  server {{
    listen {listen};
    server_name {hostname};
    root {root};
    index index.html;
    location = /api {{ return 404; }}
    location ^~ /api/ {{
      proxy_pass {upstream}/;
      proxy_http_version 1.1;
      proxy_set_header Connection "";
      proxy_set_header Forwarded "";
      proxy_set_header X-Forwarded-For $remote_addr;
      proxy_set_header X-Forwarded-Host {urlsplit(public).netloc};
      proxy_set_header X-Forwarded-Proto {scheme};
      proxy_set_header Host $proxy_host;
      proxy_hide_header Cache-Control;
      proxy_hide_header Expires;
      proxy_buffering off;
      proxy_cache off;
      proxy_next_upstream off;
      proxy_connect_timeout 5s;
      proxy_read_timeout 60s;
      proxy_send_timeout 30s;
      proxy_intercept_errors off;
      {tls}
    }}
    location ^~ /assets/ {{
      # No nested add_header: security headers inherit for all static responses.
      try_files $uri =404;
      limit_except GET {{ deny all; }}
    }}
    location / {{
      try_files $uri $uri/ =404;
      limit_except GET {{ deny all; }}
    }}
  }}
}}
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--api-origin", required=True)
    parser.add_argument("--public-origin", required=True)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--ca-bundle", type=Path)
    args = parser.parse_args()
    config = render(args.dist, args.prefix, args.api_origin, args.public_origin,
                    args.port, local=args.local, bind=args.bind, ca_bundle=args.ca_bundle)
    args.prefix.mkdir(parents=True, exist_ok=True)
    for name in ("body", "proxy"):
        (args.prefix / name).mkdir(exist_ok=True)
    (args.prefix / "nginx.conf").write_text(config, encoding="utf-8")
    print(args.prefix / "nginx.conf")


if __name__ == "__main__":
    main()
