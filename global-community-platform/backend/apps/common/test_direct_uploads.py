"""Direct-to-storage uploads, end to end against a fake Supabase Storage server."""
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.discussions.models import DiscussionAttachment
from apps.stories.models import Story

from .test_supabase_storage import KEY, FakeSupabase

User = get_user_model()
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4096


def jpeg(size=(800, 600)):
    buf = BytesIO()
    Image.new("RGB", size, (30, 140, 90)).save(buf, "JPEG")
    return buf.getvalue()


class DirectUploadTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeSupabase)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.settings_override = override_settings(
            SUPABASE_URL=cls.url, SUPABASE_SERVICE_ROLE_KEY=KEY, SUPABASE_STORAGE_BUCKET="media", SUPABASE_URL_EXPIRE=600,
            STORAGES={"default": {"BACKEND": "apps.common.supabase_storage.SupabaseStorage"},
                      "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}},
            MEDIA_REDIRECT_TO_STORAGE=True,
        )
        cls.settings_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.settings_override.disable()
        cls.server.shutdown()
        super().tearDownClass()

    def setUp(self):
        FakeSupabase.objects.clear()
        FakeSupabase.uploads.clear()
        self.user = User.objects.create_user("uploader", password="x")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def upload(self, purpose, content_type, data):
        """What the browser does: ask for a URL, then PUT the bytes there (no API key)."""
        ticket = self.client.post("/api/v1/uploads/", {"purpose": purpose, "content_type": content_type, "size": len(data)}, format="json")
        self.assertEqual(ticket.status_code, 201, ticket.data)
        self.assertTrue(ticket.data["key"].startswith(f"incoming/{self.user.pk}/"))
        request = urllib.request.Request(ticket.data["upload_url"], data=data, method="PUT", headers=ticket.data["headers"])
        with urllib.request.urlopen(request) as response:
            self.assertEqual(response.status, 200)
        return ticket.data["key"]

    def poster(self):
        return SimpleUploadedFile("poster.jpg", jpeg((720, 1280)), content_type="image/jpeg")

    def test_config_reports_direct_uploads(self):
        config = self.client.get("/api/v1/uploads/config/").data
        self.assertEqual((config["direct"], config["max_video_mb"]), (True, 50))

    def test_video_post_from_a_direct_upload_is_moved_not_copied(self):
        key = self.upload("post-video", "video/mp4", MP4)
        response = self.client.post("/api/v1/posts/video/", {"video_key": key, "poster": self.poster(), "duration_ms": "8000", "caption": "Big one"}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        attachment = DiscussionAttachment.objects.get(content_type="video/mp4")
        self.assertTrue(attachment.file.name.startswith("discussion_attachments/"))
        self.assertIn(attachment.file.name, FakeSupabase.objects)
        self.assertNotIn(key, FakeSupabase.objects, "the incoming copy is gone (moved)")
        self.assertEqual(attachment.size, len(MP4))
        video = APIClient().get(response.data["attachments"][0]["video_url"])
        self.assertEqual(video.status_code, 302, "served as a signed storage link")
        self.assertIn("/object/sign/media/discussion_attachments/", video["Location"])

    def test_photo_post_from_direct_uploads_is_processed_and_originals_removed(self):
        keys = [self.upload("post-photo", "image/jpeg", jpeg()) for _ in range(2)]
        response = self.client.post("/api/v1/posts/", {"image_keys": keys, "alt_texts": ["one", "two"], "caption": "Two photos"}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual([a["alt_text"] for a in response.data["attachments"]], ["one", "two"])
        self.assertFalse([name for name in FakeSupabase.objects if name.startswith("incoming/")])
        self.assertTrue(all(a["display_url"] for a in response.data["attachments"]))

    def test_story_video_from_a_direct_upload(self):
        key = self.upload("story-video", "video/mp4", MP4)
        response = self.client.post("/api/v1/stories/", {"media_type": "video", "file_key": key, "duration_ms": "9000"}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        story = Story.objects.get()
        self.assertTrue(story.media.name.startswith("stories/"))
        self.assertNotIn(key, FakeSupabase.objects)

    def test_someone_elses_or_unfinished_upload_is_refused(self):
        key = self.upload("post-video", "video/mp4", MP4)
        thief = User.objects.create_user("thief", password="x")
        other = APIClient()
        other.force_authenticate(thief)
        stolen = other.post("/api/v1/posts/video/", {"video_key": key, "poster": self.poster(), "duration_ms": "8000"}, format="multipart")
        self.assertEqual(stolen.status_code, 400)
        wrong_purpose = self.client.post("/api/v1/posts/", {"image_keys": [key]}, format="multipart")
        self.assertEqual(wrong_purpose.status_code, 400)
        ticket = self.client.post("/api/v1/uploads/", {"purpose": "post-video", "content_type": "video/mp4", "size": 100}, format="json").data
        unfinished = self.client.post("/api/v1/posts/video/", {"video_key": ticket["key"], "poster": self.poster(), "duration_ms": "8000"}, format="multipart")
        self.assertEqual(unfinished.status_code, 400)

    def test_fake_video_is_rejected_and_removed(self):
        key = self.upload("post-video", "video/mp4", b"definitely not a video" * 10)
        response = self.client.post("/api/v1/posts/video/", {"video_key": key, "poster": self.poster(), "duration_ms": "8000"}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(key, FakeSupabase.objects)

    def test_upload_requests_are_validated(self):
        bad_type = self.client.post("/api/v1/uploads/", {"purpose": "post-video", "content_type": "application/zip", "size": 10}, format="json")
        self.assertEqual(bad_type.status_code, 400)
        photo_as_video = self.client.post("/api/v1/uploads/", {"purpose": "post-video", "content_type": "image/jpeg", "size": 10}, format="json")
        self.assertEqual(photo_as_video.status_code, 400)
        too_big = self.client.post("/api/v1/uploads/", {"purpose": "post-video", "content_type": "video/mp4", "size": 51 * 1024 * 1024}, format="json")
        self.assertEqual(too_big.status_code, 400)
        self.assertEqual(APIClient().post("/api/v1/uploads/", {}, format="json").status_code, 401)


class WithoutObjectStorageTests(TestCase):
    def test_local_disk_reports_no_direct_uploads(self):
        user = User.objects.create_user("local", password="x")
        client = APIClient()
        client.force_authenticate(user)
        self.assertFalse(client.get("/api/v1/uploads/config/").data["direct"])
        self.assertEqual(client.post("/api/v1/uploads/", {"purpose": "post-video", "content_type": "video/mp4", "size": 10}, format="json").status_code, 400)
