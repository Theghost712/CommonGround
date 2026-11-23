"""Server-side video conversion, document scanning and the in-process job scheduler."""

import io
import os
import socket
import subprocess
import tempfile
import threading
import zipfile
import zlib
from datetime import timedelta
from io import BytesIO, StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from apps.common import jobs, video
from apps.common.scanning import EICAR, UnsafeFile, scan_document

User = get_user_model()
FFMPEG = video.ffmpeg_exe()


def make_video(seconds=1, size="320x240", rate=25, extra=()):
    """A real little clip made with the bundled ffmpeg (test pattern + tone)."""
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "clip.mov")
        subprocess.run([
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size={size}:rate={rate}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-c:v", "mpeg4", "-c:a", "pcm_s16le", "-metadata", "location=+03.0000+020.0000/", *extra, path,
        ], check=True, timeout=60)
        with open(path, "rb") as handle:
            return handle.read()


def poster():
    buf = BytesIO()
    Image.new("RGB", (320, 240), (20, 120, 200)).save(buf, "JPEG")
    return SimpleUploadedFile("poster.jpg", buf.getvalue(), content_type="image/jpeg")


@override_settings(VIDEO_TRANSCODE="sync", VIDEO_TRANSCODE_MAX_SIDE=160)
class VideoConversionTests(APITestCase):
    def setUp(self):
        if FFMPEG is None:
            self.skipTest("ffmpeg (imageio-ffmpeg) isn't installed")
        self.author = User.objects.create_user("director", password="x")
        self.client.force_authenticate(self.author)

    def post_video(self, upload):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/v1/posts/video/", {"video": upload, "poster": poster(), "duration_ms": "1000"}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def test_video_post_is_converted_to_small_h264_mp4_without_metadata(self):
        original = make_video(size="640x360")
        upload = SimpleUploadedFile("clip.mov", original, content_type="video/quicktime")
        response = self.post_video(upload)
        from apps.discussions.models import DiscussionAttachment

        attachment = DiscussionAttachment.objects.get()
        self.assertEqual(attachment.processing, "")
        self.assertEqual(attachment.content_type, "video/mp4")
        self.assertTrue(attachment.file.name.endswith(".mp4"))
        self.assertEqual((attachment.width, attachment.height), (160, 90), "long side capped, aspect kept")
        with attachment.file.open("rb") as handle:
            converted = handle.read()
        self.assertNotEqual(converted, original)
        self.assertEqual(converted[4:8], b"ftyp")
        self.assertNotIn(b"+03.0000+020.0000", converted, "location metadata is stripped")
        # "faststart": the index (moov) comes before the media data (mdat).
        self.assertLess(converted.find(b"moov"), converted.find(b"mdat"))
        width, height, duration_ms = video.probe(attachment.file.path)
        self.assertEqual((width, height), (160, 90))
        self.assertAlmostEqual(duration_ms, 1000, delta=150)
        leftovers = [name for name in os.listdir(os.path.dirname(attachment.file.path)) if name.endswith(".mov")]
        self.assertEqual(leftovers, [], "the original is deleted")

        # The URL changes with the file, so cached bytes of the original aren't reused.
        streamed = APIClient().get(self.client.get(f"/api/v1/discussions/{attachment.discussion_id}/").data["attachments"][0]["video_url"])
        self.assertEqual(streamed.status_code, 200)

    def test_story_video_is_converted(self):
        upload = SimpleUploadedFile("clip.mov", make_video(), content_type="video/quicktime")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post("/api/v1/stories/", {"media_type": "video", "file": upload, "duration_ms": 1000}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        from apps.stories.models import Story

        story = Story.objects.get()
        self.assertEqual(story.processing, "")
        self.assertTrue(story.media.name.endswith(".mp4"))

    def test_a_file_that_isnt_a_video_is_removed(self):
        # Passes the signature check (MP4 header) but ffmpeg can't decode it.
        fake = b"\x00\x00\x00\x18ftypmp42" + os.urandom(4096)
        upload = SimpleUploadedFile("clip.mp4", fake, content_type="video/mp4")
        response = self.post_video(upload)
        from apps.discussions.models import DiscussionAttachment

        attachment = DiscussionAttachment.objects.get()
        self.assertEqual(attachment.processing, "failed")
        self.assertFalse(attachment.file)
        post = self.client.get(f"/api/v1/discussions/{attachment.discussion_id}/").data
        self.assertEqual(post["attachments"][0]["video_url"], "")
        self.assertEqual(post["attachments"][0]["processing"], "failed")

    def test_pending_videos_left_behind_are_picked_up(self):
        from apps.discussions.models import DiscussionAttachment

        with override_settings(VIDEO_TRANSCODE="off"):
            upload = SimpleUploadedFile("clip.mov", make_video(), content_type="video/quicktime")
            self.client.post("/api/v1/posts/video/", {"video": upload, "poster": poster(), "duration_ms": "1000"}, format="multipart")
        DiscussionAttachment.objects.update(processing="pending")  # e.g. the server restarted mid-way
        self.assertEqual(video.process_pending_videos(), 1)
        attachment = DiscussionAttachment.objects.get()
        self.assertEqual((attachment.processing, attachment.content_type), ("", "video/mp4"))
        self.assertIsNone(video.process("discussions.DiscussionAttachment", attachment.pk), "nothing left to claim")


class DocumentScanTests(SimpleTestCase):
    def docx(self, extra=None):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            archive.writestr("[Content_Types].xml", '<Types><Default Extension="xml" ContentType="application/xml"/></Types>')
            archive.writestr("word/document.xml", "<w:document>Hello</w:document>")
            archive.writestr("word/_rels/document.xml.rels", "<Relationships/>")
            for name, content in (extra or {}).items():
                archive.writestr(name, content)
        return buf.getvalue()

    def pdf(self, body):
        return b"%PDF-1.7\n1 0 obj\n" + body + b"\nendobj\ntrailer\n%%EOF"

    def test_clean_files_pass(self):
        scan_document(self.pdf(b"<< /Type /Catalog /Pages 2 0 R >>"), "pdf")
        scan_document(self.docx(), "docx")
        scan_document("Habari, dunia ✓".encode(), "txt")
        scan_document(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512 + "WordDocument".encode("utf-16-le"), "doc")

    def assertRejected(self, data, extension):
        with self.assertRaises(UnsafeFile):
            scan_document(data, extension)

    def test_renamed_and_test_malware_files_are_rejected(self):
        self.assertRejected(b"MZ\x90\x00 this is an exe", "pdf")
        self.assertRejected(b"MZ\x90\x00 this is an exe", "docx")
        self.assertRejected(b"MZ\x90\x00 this is an exe", "doc")
        self.assertRejected(b"MZ\x90\x00\x00\x00\x03\x00", "txt")
        self.assertRejected(EICAR, "txt")

    def test_active_pdf_content_is_rejected_even_when_hidden(self):
        self.assertRejected(self.pdf(b"<< /OpenAction << /S /JavaScript /JS (app.alert(1)) >> >>"), "pdf")
        self.assertRejected(self.pdf(b"<< /S /J#61vaScript >>"), "pdf")
        self.assertRejected(self.pdf(b"<< /S /Launch /F (cmd.exe) >>"), "pdf")
        hidden = zlib.compress(b"<< /Names << /EmbeddedFiles 3 0 R >> >>")
        self.assertRejected(self.pdf(b"<< /Filter /FlateDecode >>\nstream\n" + hidden + b"\nendstream"), "pdf")

    def test_word_macros_embeds_and_remote_templates_are_rejected(self):
        self.assertRejected(self.docx({"word/vbaProject.bin": b"\x00" * 10}), "docx")
        self.assertRejected(self.docx({"word/embeddings/oleObject1.bin": b"\x00"}), "docx")
        remote = '<Relationships><Relationship Type="http://x/attachedTemplate" Target="http://evil/t.dotm" TargetMode="External"/></Relationships>'
        self.assertRejected(self.docx({"word/_rels/settings.xml.rels": remote}), "docx")
        self.assertRejected(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + "_VBA_PROJECT".encode("utf-16-le"), "doc")


class FakeClamd:
    """A tiny clamd speaking INSTREAM: flags anything containing b'VIRUS'."""

    def __init__(self):
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen()
        self.port = self.server.getsockname()[1]
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with conn:
                data = b""
                while not data.endswith(b"\x00\x00\x00\x00"):
                    part = conn.recv(65536)
                    if not part:
                        break
                    data += part
                conn.sendall(b"stream: Fake.Virus FOUND\x00" if b"VIRUS" in data else b"stream: OK\x00")

    def close(self):
        self.server.close()


class ClamavTests(SimpleTestCase):
    def test_clamd_verdicts_and_outage(self):
        clamd = FakeClamd()
        try:
            with override_settings(CLAMD_HOST="127.0.0.1", CLAMD_PORT=clamd.port):
                scan_document(b"just some text", "txt")
                with self.assertRaisesMessage(UnsafeFile, "malware"):
                    scan_document(b"text with a VIRUS inside", "txt")
        finally:
            clamd.close()
        unused = socket.socket()
        unused.bind(("127.0.0.1", 0))
        port = unused.getsockname()[1]
        unused.close()  # nothing listens there: clamd is "down"
        with override_settings(CLAMD_HOST="127.0.0.1", CLAMD_PORT=port):
            with self.assertRaisesMessage(UnsafeFile, "couldn't check"):
                scan_document(b"text", "txt")
            with override_settings(CLAMD_FAIL_OPEN=True):
                scan_document(b"text", "txt")


class AttachmentScanTests(APITestCase):
    def test_upload_endpoint_rejects_dangerous_documents(self):
        from apps.communities.models import Community, CommunityMembership
        from apps.discussions.models import Discussion

        owner = User.objects.create_user("scan_owner", password="x")
        community = Community.objects.create(name="Scanners", slug="scanners", description="x", created_by=owner, approval_status="approved")
        CommunityMembership.objects.get_or_create(community=community, user=owner, defaults={"status": CommunityMembership.ACTIVE})
        discussion = Discussion.objects.create(community=community, author=owner, title="Docs", body="See attached")
        self.client.force_authenticate(owner)
        url = f"/api/v1/discussions/{discussion.id}/attachments/"
        bad = SimpleUploadedFile("invoice.pdf", b"%PDF-1.4\n<< /OpenAction << /JS (x) >> >>", content_type="application/pdf")
        response = self.client.post(url, {"file": bad}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("scripts", str(response.data["file"]))
        good = SimpleUploadedFile("notes.txt", b"Meeting at 5", content_type="text/plain")
        self.assertEqual(self.client.post(url, {"file": good}, format="multipart").status_code, 201)
        fake_image = SimpleUploadedFile("photo.png", b"MZ not a png", content_type="application/octet-stream")
        self.assertEqual(self.client.post(url, {"file": fake_image}, format="multipart").status_code, 400, "images are always decoded")


class SchedulerTests(TestCase):
    def test_due_jobs_run_once_per_interval(self):
        calls = []
        fake_jobs = [("a", 60, lambda: calls.append("a")), ("b", 60, lambda: 1 / 0), ("c", 60, lambda: calls.append("c"))]
        with mock.patch.object(jobs, "JOBS", fake_jobs):
            self.assertEqual(jobs.run_due_jobs(), ["a", "c"], "a failing job doesn't stop the others")
            self.assertEqual(jobs.run_due_jobs(), [], "not due again yet")
        self.assertEqual(calls, ["a", "c"])

    def test_tick_endpoint(self):
        with mock.patch.object(jobs, "JOBS", [("noop", 60, lambda: None)]):
            self.assertEqual(self.client.get("/api/v1/internal/tick/").json(), {"ran": ["noop"]})
            self.assertEqual(self.client.post("/api/v1/internal/tick/").json(), {"ran": []})
            cache.clear()
            with override_settings(CRON_SECRET="s3cret"):
                self.assertEqual(self.client.get("/api/v1/internal/tick/").status_code, 403)
                ok = self.client.get("/api/v1/internal/tick/", HTTP_AUTHORIZATION="Bearer s3cret")
                self.assertEqual(ok.json(), {"ran": ["noop"]})

    def test_real_jobs_run(self):
        self.assertEqual(set(jobs.run_due_jobs()), {name for name, _, _ in jobs.JOBS})


class ReminderCatchUpTests(TestCase):
    def test_a_late_run_still_sends_the_one_hour_reminder(self):
        from apps.communities.models import Community, CommunityMembership
        from apps.events.models import CommunityEvent, EventRSVP
        from apps.notifications.models import Notification

        owner = User.objects.create_user("late_owner", password="x")
        guest = User.objects.create_user("late_guest", password="x")
        community = Community.objects.create(name="Late", slug="late", description="x", created_by=owner, approval_status="approved")
        CommunityMembership.objects.get_or_create(community=community, user=guest, defaults={"status": CommunityMembership.ACTIVE})
        event = CommunityEvent.objects.create(
            community=community, created_by=owner, title="Meetup", starts_at=timezone.now() + timedelta(minutes=35),
            ends_at=timezone.now() + timedelta(hours=2),
        )
        EventRSVP.objects.create(event=event, user=guest, response=EventRSVP.GOING)
        call_command("send_event_reminders", stdout=StringIO())
        reminder = Notification.objects.get(recipient=guest, notification_type=Notification.EVENT_REMINDER)
        self.assertIn("in 35 minutes", reminder.body)
