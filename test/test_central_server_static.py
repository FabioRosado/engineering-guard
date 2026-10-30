"""Static serving of the built UI by the central factory server (decisions/factory-visual-handover.md, B).

A real server runs on an ephemeral loopback port with its data directory and UI directory pointed
at temporary folders, so these tests never touch ~/.engineering-guard-factory. The path-traversal
cases are the point: the handler subclasses SimpleHTTPRequestHandler, which can serve any file, so
the allowlist has to hold against hostile paths sent over a real socket.
"""

import http.client
import importlib.util
import socket
import socketserver
import tempfile
import threading
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVER_SCRIPT = PROJECT_ROOT / ".agents" / "skills" / "factory" / "scripts" / "central_factory_server.py"


def load_server_module():
    spec = importlib.util.spec_from_file_location("central_factory_server_under_test", SERVER_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StaticServingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="factory-static-")
        root = Path(self.temp.name)
        self.ui_dist = root / "ui" / "dist"
        (self.ui_dist / "assets").mkdir(parents=True)
        (self.ui_dist / "index.html").write_text("<!doctype html><title>factory</title>", encoding="utf-8")
        (self.ui_dist / "assets" / "app.js").write_text("console.log('app')", encoding="utf-8")
        (self.ui_dist / "assets" / "app.css").write_text("body{}", encoding="utf-8")
        (self.ui_dist / "assets" / "blob.bin").write_bytes(b"\x00\x01")
        # A file next to dist/ that must never be reachable through it.
        (root / "ui" / "secret.txt").write_text("outside dist", encoding="utf-8")
        (root / "outside.txt").write_text("outside", encoding="utf-8")

        self.module = load_server_module()
        self.module.DATA_DIR = root / "data"
        self.module.DATA_FILE = self.module.DATA_DIR / "data.json"
        self.module.ARCHIVE_FILE = self.module.DATA_DIR / "archive.json"
        self.module.UI_DIST_DIR = self.ui_dist
        self.module.DATA_DIR.mkdir(parents=True)

        socketserver.TCPServer.allow_reuse_address = True
        self.httpd = socketserver.TCPServer(("127.0.0.1", 0), self.module.JobServer)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self.temp.cleanup()

    def get(self, path, method="GET"):
        # http.client sends the path exactly as given, unlike urllib which would normalise ".."
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_root_serves_the_built_index(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b"<title>factory</title>", body)

    def test_assets_are_served_with_their_content_types(self):
        status, headers, body = self.get("/assets/app.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers["Content-Type"])
        self.assertEqual(body, b"console.log('app')")
        self.assertIn("text/css", self.get("/assets/app.css")[1]["Content-Type"])

    def test_unknown_file_types_are_not_sniffed(self):
        status, headers, _ = self.get("/assets/blob.bin")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/octet-stream")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_every_static_response_forbids_sniffing(self):
        for path in ("/", "/assets/app.js", "/assets/app.css"):
            self.assertEqual(self.get(path)[1]["X-Content-Type-Options"], "nosniff", path)

    def test_a_missing_asset_is_404_not_the_index(self):
        # Serving index.html for unknown paths would hide a broken build behind a blank page.
        self.assertEqual(self.get("/assets/missing.js")[0], 404)

    def test_paths_that_escape_the_ui_directory_are_refused(self):
        hostile = [
            "/../secret.txt",
            "/assets/../../secret.txt",
            "/assets/../../../outside.txt",
            "/%2e%2e/secret.txt",
            "/assets/%2e%2e/%2e%2e/secret.txt",
            "/assets/..%2f..%2fsecret.txt",
            "/%2e%2e%2f%2e%2e%2foutside.txt",
            "//etc/passwd",
            "/assets//..//..//secret.txt",
            "/assets/\\..\\..\\secret.txt",
            "/assets/app.js%00.txt",
        ]
        for path in hostile:
            with self.subTest(path=path):
                status, _, body = self.get(path)
                self.assertIn(status, (400, 404), f"{path} returned {status}")
                self.assertNotIn(b"outside", body)

    def test_a_symlink_pointing_outside_dist_is_refused(self):
        link = self.ui_dist / "assets" / "escape.txt"
        link.symlink_to(self.ui_dist.parent / "secret.txt")
        status, _, body = self.get("/assets/escape.txt")
        self.assertIn(status, (403, 404))
        self.assertNotIn(b"outside dist", body)

    def test_a_directory_is_not_listed(self):
        status, _, body = self.get("/assets/")
        self.assertIn(status, (403, 404))
        self.assertNotIn(b"app.js", body)

    def test_dotfiles_and_server_source_are_not_reachable(self):
        for path in ("/.env", "/central_factory_server.py", "/../scripts/factory_board.py"):
            self.assertIn(self.get(path)[0], (400, 403, 404), path)

    def test_the_api_keeps_priority_over_static_files(self):
        (self.ui_dist / "api").mkdir()
        (self.ui_dist / "api" / "jobs").write_text("not the api", encoding="utf-8")
        status, _, body = self.get("/api/jobs")
        self.assertEqual(status, 200)
        self.assertIn(b'"jobs"', body)

    def test_an_unbuilt_ui_explains_how_to_build_it(self):
        (self.ui_dist / "index.html").unlink()
        status, _, body = self.get("/")
        self.assertEqual(status, 503)
        self.assertIn(b"npm", body)
        self.assertIn(b"build", body)

    def test_head_requests_do_not_return_a_body(self):
        status, headers, body = self.get("/", method="HEAD")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")

    def test_a_silent_connection_does_not_block_other_requests_for_long(self):
        # The server handles one connection at a time. A browser's speculative connection sends
        # nothing, and without a timeout it would hold the server (and every board push) forever.
        self.assertGreater(self.module.JobServer.timeout, 0, "the handler must set a request timeout")
        self.module.JobServer.timeout = 1  # production uses a few seconds; keep the test quick
        silent = socket.create_connection(("127.0.0.1", self.port))
        self.addCleanup(silent.close)
        started = time.monotonic()
        status, _, _ = self.get("/health")
        self.assertEqual(status, 200)
        self.assertLess(time.monotonic() - started, 4, "the silent connection blocked the server")

    def test_health_still_works(self):
        status, _, body = self.get("/health")
        self.assertEqual(status, 200)
        self.assertIn(b"ok", body)


if __name__ == "__main__":
    unittest.main()
