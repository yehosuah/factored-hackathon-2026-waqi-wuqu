"""Production config boundaries; integration requires nginx and local socket access."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

spec = importlib.util.spec_from_file_location("render_nginx", Path(__file__).with_name("render_nginx.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ConfigTests(unittest.TestCase):
    def test_http_public_origin_requires_loopback_bind_even_with_local_flag(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text("synthetic")
            for bind in ["0.0.0.0", "::", "192.168.1.5", "10.0.0.5", "fd00::1"]:
                with self.subTest(bind=bind), self.assertRaisesRegex(ValueError, "loopback listen"):
                    module.render(root, root, "http://127.0.0.1:18023", "http://localhost:8080", 8080, local=True, bind=bind)
            for bind in ["127.0.0.1", "127.0.0.2", "::1"]:
                self.assertIn("listen", module.render(root, root, "http://127.0.0.1:18023", "http://localhost:8080", 8080, local=True, bind=bind))
            # A separate HTTPS edge may forward to the non-root internal listener.
            self.assertIn("listen 0.0.0.0:8080", module.render(root, root, "http://127.0.0.1:18023", "https://demo.example", 8080, local=True, bind="0.0.0.0"))

    def test_cleartext_api_requires_explicit_local_loopback_including_private_networks(self):
        for value in ["http://public.example", "http://api.internal", "http://host.docker.internal:18023", "http://10.0.0.5", "http://192.168.1.5", "http://172.17.0.2", "http://[fd00::1]", "http://localhost.example"]:
            for local in [False, True]:
                with self.subTest(value=value, local=local), self.assertRaises(ValueError):
                    module.origin(value, upstream=True, local=local)
        for value in ["http://127.0.0.1:18023", "http://localhost:18023", "http://[::1]:18023"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.origin(value, upstream=True)
            self.assertEqual(module.origin(value, upstream=True, local=True)[0], value)
        self.assertEqual(module.origin("https://host.docker.internal:18177", upstream=True)[0], "https://host.docker.internal:18177")

    def test_origins_cannot_inject_config_or_select_remote_http_public_origin(self):
        for value in ["http://user:password@localhost", "http://localhost/path", "http://localhost/?x=1", "http://localhost/#x", "http://localhost;return 200;", "http://localhost\n", "http://localhost:0", "http://localhost:65536"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.origin(value, upstream=True)
        for value in ["http://public.example", "http://127.0.0.1"]:
            with self.assertRaises(ValueError):
                module.origin(value)
        self.assertEqual(module.origin("https://api.internal:8443", upstream=True)[0], "https://api.internal:8443")
        self.assertEqual(module.origin("http://127.0.0.1:8080", local=True)[1], "127.0.0.1")

    def test_paths_reject_nginx_variable_quote_and_control_injection(self):
        for path in ['/tmp/$evil', '/tmp/quote"', '/tmp/line\n', '/tmp/back\\slash']:
            with self.assertRaises(ValueError):
                module.quoted_path(Path(path))


@unittest.skipUnless(os.getenv("FACTORED_SERVING_INTEGRATION") == "1", "opt-in local Nginx integration")
class ServingTests(unittest.TestCase):
    def test_real_nginx_serves_build_preserves_contract_and_never_retries_mutations(self):
        binary = shutil.which("nginx")
        self.assertIsNotNone(binary)
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                calls.append({"path": self.path, "body": body, "authorization": self.headers.get("Authorization"), "key": self.headers.get("Idempotency-Key"), "proto": self.headers.get("X-Forwarded-Proto"), "forwarded": self.headers.get("Forwarded")})
                self.send_response(503 if self.path == "/unavailable" else 200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "public")
                self.end_headers()
                self.wfile.write(b'{"synthetic":true}')

        upstream = HTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=upstream.serve_forever, daemon=True)
        worker.start()
        with tempfile.TemporaryDirectory(prefix="factored-serving-") as temporary:
            prefix = Path(temporary)
            for name in ("body", "proxy"):
                (prefix / name).mkdir()
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                port = probe.getsockname()[1]
            dist = Path(__file__).resolve().parents[1] / "dist"
            config = module.render(dist, prefix, f"http://127.0.0.1:{upstream.server_port}", f"http://127.0.0.1:{port}", port, local=True)
            (prefix / "nginx.conf").write_text(config)
            command = [binary, "-e", "stderr", "-p", str(prefix), "-c", str(prefix / "nginx.conf")]
            subprocess.run(command + ["-t"], check=True, capture_output=True)
            process = subprocess.Popen(command + ["-g", "daemon off;"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                import time
                base = f"http://127.0.0.1:{port}"
                for _ in range(50):
                    try:
                        response = urlopen(base, timeout=1)
                        break
                    except OSError:
                        time.sleep(.05)
                else:
                    self.fail("Nginx did not listen")
                with response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), (dist / "index.html").read_bytes())
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
                    self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                    self.assertEqual(response.headers["X-Frame-Options"], "DENY")
                asset = next((dist / "assets").glob("*.js"))
                with urlopen(base + "/assets/" + asset.name) as response:
                    self.assertIn("immutable", response.headers["Cache-Control"])
                    self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
                    self.assertEqual(hashlib.sha256(response.read()).digest(), hashlib.sha256(asset.read_bytes()).digest())
                body = json.dumps({"message": "synthetic proxy check"}).encode()
                for path in ["/api/me/conversations/test/turns?limit=2", "/api/unavailable"]:
                    request = Request(base + path, body, {"Content-Type": "application/json", "Authorization": "Bearer synthetic-proxy-check", "Idempotency-Key": "synthetic-key", "Forwarded": "proto=http;host=untrusted", "X-Forwarded-Proto": "untrusted"})
                    try:
                        response = urlopen(request)
                    except HTTPError as error:
                        response = error
                    with response:
                        self.assertEqual(response.headers["Cache-Control"], "no-store")
                        self.assertEqual(response.read(), b'{"synthetic":true}')
                        self.assertEqual(response.status, 503 if path.endswith("unavailable") else 200)
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0]["path"], "/me/conversations/test/turns?limit=2")
                for call in calls:
                    self.assertEqual(call["body"], body)
                    self.assertEqual(call["authorization"], "Bearer synthetic-proxy-check")
                    self.assertEqual(call["key"], "synthetic-key")
                    self.assertEqual(call["proto"], "http")
                    self.assertIsNone(call["forwarded"])
                for path in ["/assets/missing.js", "/unknown", "/api"]:
                    with self.assertRaises(HTTPError) as error:
                        urlopen(base + path)
                    self.assertEqual(error.exception.code, 404)
                    self.assertEqual(error.exception.headers["Cache-Control"], "no-store")
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(base, headers={"Host": "attacker.invalid"}))
                self.assertEqual(error.exception.code, 421)
                self.assertEqual(error.exception.headers["X-Content-Type-Options"], "nosniff")
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(base + "/api/oversized", b"x" * (128 * 1024 + 1)))
                self.assertEqual(error.exception.code, 413)
                self.assertEqual(len(calls), 2)
            finally:
                process.terminate()
                _, error_log = process.communicate(timeout=10)
                self.assertNotIn(b"synthetic-proxy-check", error_log)
                upstream.shutdown()
                upstream.server_close()


if __name__ == "__main__":
    unittest.main()
