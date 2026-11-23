import os
import tempfile
from datetime import datetime, timedelta, timezone as dt_timezone
from io import BytesIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile
from apps.discussions.models import Discussion, DiscussionAttachment

from .usage import measure_storage, usage_summary

User = get_user_model()


def jpeg():
    buf = BytesIO()
    Image.new("RGB", (900, 700), (10, 120, 200)).save(buf, "JPEG")
    return SimpleUploadedFile("pic.jpg", buf.getvalue(), content_type="image/jpeg")


class LinkPreviewTests(TestCase):
    def setUp(self):
        self.dist = tempfile.mkdtemp()
        Path(self.dist, "index.html").write_text('<html><head><meta name="description" content="x" /><title>CommonGround — Ideas build communities</title></head><body></body></html>')
        self.override = override_settings(FRONTEND_DIST=Path(self.dist))
        self.override.enable()
        self.author = User.objects.create_user("asha", password="x", first_name="Asha", last_name="J")

    def tearDown(self):
        self.override.disable()

    def test_public_photo_post_gets_title_text_and_jpeg_image(self):
        client = APIClient()
        client.force_authenticate(self.author)
        post = client.post("/api/v1/posts/", {"images": [jpeg()], "caption": "Sunset over Lake Victoria <3"}, format="multipart").data
        html = self.client.get(f"/discussions/{post['id']}").content.decode()
        self.assertIn('<meta property="og:title" content="Asha J on CommonGround" />', html)
        self.assertIn("Sunset over Lake Victoria &lt;3", html, "text is escaped")
        attachment = DiscussionAttachment.objects.get()
        self.assertIn(f"/og-image/{attachment.pk}.jpg", html)
        self.assertIn("<title>Asha J on CommonGround</title>", html)
        image = self.client.get(f"/og-image/{attachment.pk}.jpg")
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image["Content-Type"], "image/jpeg")
        self.assertTrue(image.content.startswith(b"\xff\xd8"))

    def test_private_things_get_the_generic_preview(self):
        UserProfile.objects.update_or_create(user=self.author, defaults={"is_private": True})
        post = Discussion.objects.create(author=self.author, title="", body="Only for followers")
        html = self.client.get(f"/discussions/{post.pk}").content.decode()
        self.assertNotIn("Only for followers", html)
        self.assertIn("CommonGround — Ideas build communities", html)
        self.assertNotIn("Asha", self.client.get("/u/asha").content.decode())
        self.assertEqual(self.client.get("/og-image/999.jpg").status_code, 404)

    def test_public_profile_preview(self):
        UserProfile.objects.update_or_create(user=self.author, defaults={"bio": "Photographer in Mwanza"})
        html = self.client.get("/u/asha").content.decode()
        self.assertIn("Asha J (@asha) · CommonGround", html)
        self.assertIn("Photographer in Mwanza", html)


class UsageTests(TestCase):
    def test_summary_and_local_storage_measure(self):
        with tempfile.TemporaryDirectory() as root, override_settings(MEDIA_ROOT=root):
            Path(root, "a.bin").write_bytes(b"x" * 2048)
            result = measure_storage()
            self.assertEqual((result["bytes"], result["files"]), (2048, 1))
            items = {item["label"]: item for item in usage_summary()}
            self.assertEqual(items["Media storage"]["used"], 2048)
            self.assertEqual(items["Media storage"]["level"], "ok")
            self.assertIsNotNone(items["Database"]["used"])

    def test_remote_walk_removes_abandoned_uploads(self):
        old = (datetime.now(dt_timezone.utc) - timedelta(days=3)).isoformat()
        new = datetime.now(dt_timezone.utc).isoformat()
        fake = mock.Mock()
        fake.walk.return_value = [("incoming/1/old.mp4", 5000, old), ("incoming/1/new.mp4", 100, new), ("discussion_attachments/x.mp4", 700, old)]
        with mock.patch("django.core.files.storage.default_storage", fake):
            result = measure_storage()
        fake.delete.assert_called_once_with("incoming/1/old.mp4")
        self.assertEqual((result["bytes"], result["removed_abandoned"]), (800, 1))

    def test_admin_dashboard_shows_usage_to_superusers(self):
        admin = User.objects.create_superuser("boss", "boss@example.com", "x")
        self.client.force_login(admin)
        cache.delete("usage:storage")
        html = self.client.get("/admin/").content.decode()
        self.assertIn("Free plan usage", html)
        self.assertIn("Media storage", html)
