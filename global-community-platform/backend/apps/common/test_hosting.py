import tempfile
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

User = get_user_model()


class SpaServingTests(TestCase):
    def setUp(self):
        self.dist = Path(tempfile.mkdtemp())
        (self.dist / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")

    def test_client_routes_get_the_app_shell_with_csp(self):
        with override_settings(FRONTEND_DIST=self.dist, CSP_MEDIA_ORIGINS=["https://abc.supabase.co"]):
            for path in ["/", "/home", "/u/amina", "/discussions/12", "/reset-password?uid=x&token=y"]:
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, path)
                self.assertIn(b"id=root", response.content)
            self.assertEqual(response["Cache-Control"], "no-cache")
            csp = response["Content-Security-Policy"]
            self.assertIn("script-src 'self'", csp)
            self.assertIn("media-src 'self' blob: https://abc.supabase.co", csp)
            self.assertIn("camera=(self)", response["Permissions-Policy"])

    def test_api_admin_and_ws_paths_are_not_swallowed(self):
        with override_settings(FRONTEND_DIST=self.dist):
            self.assertEqual(self.client.get("/api/v1/health/").status_code, 200)
            self.assertEqual(self.client.get("/api/v1/does-not-exist/").status_code, 404)
            self.assertNotIn(b"id=root", self.client.get("/admin/login/").content)

    def test_missing_build_is_a_404_not_a_crash(self):
        with override_settings(FRONTEND_DIST=self.dist / "nope"):
            self.assertEqual(self.client.get("/home").status_code, 404)


class StorageRedirectTests(TestCase):
    def test_media_redirects_to_signed_storage_url_without_long_cache(self):
        author = User.objects.create_user("photog2", password="x")
        client = APIClient()
        client.force_authenticate(author)
        buf = BytesIO()
        Image.new("RGB", (600, 400), (1, 2, 3)).save(buf, "JPEG")
        created = client.post("/api/v1/posts/", {"images": [SimpleUploadedFile("a.jpg", buf.getvalue(), content_type="image/jpeg")]}, format="multipart")
        self.assertEqual(created.status_code, 201, created.data)
        url = created.data["attachments"][0]["display_url"]
        with override_settings(MEDIA_REDIRECT_TO_STORAGE=True):
            response = APIClient().get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("discussion_images/", response["Location"])
        self.assertEqual(response["Cache-Control"], "private, max-age=300")
        forged = APIClient().get(url.split("?")[0] + "?t=forged")
        self.assertEqual(forged.status_code, 403, "permission is still checked before redirecting")
