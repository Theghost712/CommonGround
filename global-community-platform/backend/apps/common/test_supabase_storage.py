import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from django.core.files.base import ContentFile
from django.test import SimpleTestCase

from .supabase_storage import SupabaseStorage, SupabaseStorageError

KEY = "service-role-test-key"


class FakeSupabase(BaseHTTPRequestHandler):
    """Just enough of Supabase Storage's REST API (v1) to exercise the backend."""

    objects = {}

    def log_message(self, *args):
        pass

    def _reply(self, status, body=b"", content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        ok = self.headers.get("Authorization") == f"Bearer {KEY}" and self.headers.get("apikey") == KEY
        if not ok:
            self._reply(403, b'{"error":"unauthorized"}')
        return ok

    def _body(self):
        return self.rfile.read(int(self.headers.get("Content-Length") or 0))

    def do_POST(self):
        if not self._authorized():
            return
        path = unquote(urlparse(self.path).path)
        if path.startswith("/storage/v1/object/sign/media/"):
            name = path.removeprefix("/storage/v1/object/sign/media/")
            if name not in self.objects:
                return self._reply(400, b'{"error":"not_found"}')
            expires = json.loads(self._body())["expiresIn"]
            return self._reply(200, json.dumps({"signedURL": f"/object/sign/media/{name}?token=t{expires}"}).encode())
        name = path.removeprefix("/storage/v1/object/media/")
        if name in self.objects and self.headers.get("x-upsert") == "false":
            return self._reply(409, b'{"error":"Duplicate"}')
        self.objects[name] = (self._body(), self.headers.get("Content-Type"))
        self._reply(200, json.dumps({"Key": f"media/{name}"}).encode())

    def do_GET(self):
        if not self._authorized():
            return
        path = unquote(urlparse(self.path).path)
        if path == "/storage/v1/bucket/media":
            return self._reply(200, b'{"id":"media"}')
        if path.startswith("/storage/v1/object/info/media/"):
            name = path.removeprefix("/storage/v1/object/info/media/")
            if name not in self.objects:
                return self._reply(400, b'{"statusCode":"404","error":"not_found"}')
            return self._reply(200, json.dumps({"name": name, "size": len(self.objects[name][0])}).encode())
        name = path.removeprefix("/storage/v1/object/media/")
        if name not in self.objects:
            return self._reply(400, b'{"statusCode":"404","error":"not_found"}')
        data, content_type = self.objects[name]
        self._reply(200, data, content_type or "application/octet-stream")

    def do_DELETE(self):
        if not self._authorized():
            return
        for prefix in json.loads(self._body())["prefixes"]:
            self.objects.pop(prefix, None)
        self._reply(200, b"[]")


class SupabaseStorageTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeSupabase)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        super().tearDownClass()

    def setUp(self):
        FakeSupabase.objects.clear()
        self.storage = SupabaseStorage(url=self.url, key=KEY, bucket="media", expires=600)

    def test_save_open_size_url_delete_round_trip(self):
        upload = ContentFile(b"\x00\x01video bytes", name="clip.mp4")
        upload.content_type = "video/mp4"
        name = self.storage.save("discussion_videos/2026/11/clip one.mp4", upload)
        self.assertEqual(name, "discussion_videos/2026/11/clip one.mp4")
        self.assertEqual(FakeSupabase.objects[name][1], "video/mp4")
        self.assertTrue(self.storage.exists(name))
        self.assertEqual(self.storage.size(name), 13)
        with self.storage.open(name) as handle:
            self.assertEqual(handle.read(), b"\x00\x01video bytes")
        signed = self.storage.url(name)
        self.assertTrue(signed.startswith(f"{self.url}/storage/v1/object/sign/media/discussion_videos/2026/11/clip one.mp4?token="))
        self.assertIn("t600", signed)
        self.storage.delete(name)
        self.assertFalse(self.storage.exists(name))
        self.storage.delete(name)  # deleting twice is harmless

    def test_name_collision_gets_a_new_name_instead_of_overwriting(self):
        first = self.storage.save("a/photo.webp", ContentFile(b"one"))
        second = self.storage.save("a/photo.webp", ContentFile(b"two"))
        self.assertNotEqual(first, second)
        self.assertEqual(FakeSupabase.objects[first][0], b"one")

    def test_missing_files_and_bad_credentials(self):
        with self.assertRaises(FileNotFoundError):
            self.storage.open("nope.webp")
        with self.assertRaises(FileNotFoundError):
            self.storage.size("nope.webp")
        self.assertTrue(self.storage.check())
        wrong = SupabaseStorage(url=self.url, key="wrong", bucket="media")
        self.assertFalse(wrong.check())
        with self.assertRaises(SupabaseStorageError):
            wrong.save("x.txt", ContentFile(b"x"))
