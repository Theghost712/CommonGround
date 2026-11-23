from datetime import timedelta
from io import BytesIO, StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.messaging.models import Message
from apps.social.models import Follow

from .models import CloseFriend, Story, StoryHiddenFrom, StoryView

User = get_user_model()


def jpeg_with_gps(size=(3000, 2000)):
    buf = BytesIO()
    exif = Image.Exif()
    exif[0x010F] = "TestPhone"
    exif.get_ifd(0x8825)[2] = (3.0, 20.0, 0.0)
    Image.new("RGB", size, (30, 120, 200)).save(buf, "JPEG", exif=exif.tobytes())
    return SimpleUploadedFile("holiday.jpg", buf.getvalue(), content_type="image/jpeg")


def mp4_bytes(size=2048):
    return b"\x00\x00\x00\x18ftypmp42" + b"\x00" * (size - 12)


class StoryBase(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user(username="storyteller", password="Strong-pass-123")
        self.fan = User.objects.create_user(username="fan", password="Strong-pass-123")
        self.stranger = User.objects.create_user(username="stranger", password="Strong-pass-123")
        Follow.objects.create(follower=self.fan, following=self.author)

    def as_user(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def text_story(self, **extra):
        return Story.objects.create(author=self.author, media_type=Story.TEXT, text="Hello", **extra)


class CreateStoryTests(StoryBase):
    def test_photo_story_is_resized_to_webp_and_stripped_of_location(self):
        response = self.as_user(self.author).post("/api/v1/stories/", {"media_type": "image", "file": jpeg_with_gps(), "alt_text": "Beach at sunset"}, format="multipart")

        self.assertEqual(response.status_code, 201, response.data)
        story = Story.objects.get()
        stored = Image.open(story.media.open("rb"))
        self.assertEqual(stored.format, "WEBP")
        self.assertLessEqual(max(stored.size), 1920)
        self.assertEqual(len(stored.getexif()), 0)
        self.assertTrue(story.thumbnail)
        self.assertEqual(response.data["alt_text"], "Beach at sunset")
        self.assertTrue(response.data["media_url"].startswith(f"/api/v1/stories/{story.pk}/media/?t="))
        self.assertAlmostEqual((story.expires_at - story.created_at).total_seconds(), 24 * 3600, delta=5)

    def test_video_story_checks_signature_and_keeps_duration(self):
        good = SimpleUploadedFile("clip.mp4", mp4_bytes(), content_type="video/mp4")
        fake = SimpleUploadedFile("clip.mp4", b"this is not a video at all", content_type="video/mp4")
        ok = self.as_user(self.author).post("/api/v1/stories/", {"media_type": "video", "file": good, "duration_ms": 12000}, format="multipart")
        bad = self.as_user(self.author).post("/api/v1/stories/", {"media_type": "video", "file": fake}, format="multipart")

        self.assertEqual(ok.status_code, 201, ok.data)
        self.assertEqual(ok.data["duration_ms"], 12000)
        self.assertEqual(bad.status_code, 400)

    def test_videos_longer_than_a_minute_are_rejected(self):
        clip = SimpleUploadedFile("clip.mp4", mp4_bytes(), content_type="video/mp4")
        response = self.as_user(self.author).post("/api/v1/stories/", {"media_type": "video", "file": clip, "duration_ms": 90000}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_text_story_and_validation(self):
        ok = self.as_user(self.author).post("/api/v1/stories/", {"media_type": "text", "text": "Karibu!", "background": "sunset"}, format="json")
        empty = self.as_user(self.author).post("/api/v1/stories/", {"media_type": "text", "text": "  "}, format="json")
        no_file = self.as_user(self.author).post("/api/v1/stories/", {"media_type": "image"}, format="json")
        bad_photo = self.as_user(self.author).post("/api/v1/stories/", {"media_type": "image", "file": SimpleUploadedFile("x.jpg", b"nope", "image/jpeg")}, format="multipart")

        self.assertEqual(ok.status_code, 201)
        self.assertEqual(ok.data["background"], "sunset")
        self.assertEqual([empty.status_code, no_file.status_code, bad_photo.status_code], [400, 400, 400])
        self.assertEqual(Story.objects.count(), 1)


class VisibilityTests(StoryBase):
    def tray_usernames(self, user):
        return [entry["user"]["username"] for entry in self.as_user(user).get("/api/v1/stories/tray/").data]

    def test_followers_see_stories_strangers_do_not(self):
        story = self.text_story()
        self.assertEqual(self.tray_usernames(self.fan), ["storyteller"])
        self.assertEqual(self.tray_usernames(self.stranger), [])
        self.assertEqual(self.as_user(self.stranger).get(f"/api/v1/stories/{story.pk}/").status_code, 404)

    def test_expired_stories_disappear(self):
        self.text_story(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.tray_usernames(self.fan), [])

    def test_close_friends_stories(self):
        self.text_story(audience=Story.CLOSE_FRIENDS)
        self.assertEqual(self.tray_usernames(self.fan), [])
        self.as_user(self.author).put("/api/v1/stories/close-friends/fan/")
        self.assertEqual(self.tray_usernames(self.fan), ["storyteller"])
        self.assertEqual([p["username"] for p in self.as_user(self.author).get("/api/v1/stories/close-friends/").data], ["fan"])

    def test_hide_story_from_a_follower(self):
        self.text_story()
        self.as_user(self.author).put("/api/v1/stories/hidden-from/fan/")
        self.assertEqual(self.tray_usernames(self.fan), [])
        self.as_user(self.author).delete("/api/v1/stories/hidden-from/fan/")
        self.assertEqual(self.tray_usernames(self.fan), ["storyteller"])

    def test_tray_order_own_first_then_unseen_then_seen(self):
        other = User.objects.create_user(username="other_author", password="Strong-pass-123")
        Follow.objects.create(follower=self.fan, following=other)
        seen = self.text_story()
        Story.objects.create(author=other, media_type=Story.TEXT, text="New")
        Story.objects.create(author=self.fan, media_type=Story.TEXT, text="Mine")
        StoryView.objects.create(story=seen, viewer=self.fan)

        tray = self.as_user(self.fan).get("/api/v1/stories/tray/").data

        self.assertEqual([e["user"]["username"] for e in tray], ["fan", "other_author", "storyteller"])
        self.assertTrue(tray[2]["all_seen"])
        self.assertFalse(tray[1]["all_seen"])

    def test_user_endpoint_for_profile_ring(self):
        self.text_story()
        self.assertEqual(len(self.as_user(self.fan).get("/api/v1/stories/user/storyteller/").data), 1)
        self.assertEqual(self.as_user(self.stranger).get("/api/v1/stories/user/storyteller/").data, [])


class MediaLinkTests(StoryBase):
    def setUp(self):
        super().setUp()
        response = self.as_user(self.author).post("/api/v1/stories/", {"media_type": "video", "file": SimpleUploadedFile("c.mp4", mp4_bytes(4096), "video/mp4"), "duration_ms": 8000}, format="multipart")
        self.story = Story.objects.get(pk=response.data["id"])
        self.url = self.as_user(self.fan).get(f"/api/v1/stories/{self.story.pk}/").data["media_url"]

    def test_signed_link_serves_video_without_login_and_supports_ranges(self):
        anonymous = APIClient()
        full = anonymous.get(self.url)
        part = anonymous.get(self.url, HTTP_RANGE="bytes=0-99")

        self.assertEqual(full.status_code, 200)
        self.assertEqual(full["Content-Type"], "video/mp4")
        self.assertEqual(part.status_code, 206)
        self.assertEqual(part["Content-Range"], "bytes 0-99/4096")
        self.assertEqual(len(part.content), 100)

    def test_tampered_or_expired_links_are_refused(self):
        cut = self.url.index("&v=")  # tamper with the signature, not the cache-busting version
        tampered = self.url[:cut - 3] + "abc" + self.url[cut:]
        self.assertEqual(APIClient().get(tampered).status_code, 403)
        with mock.patch("apps.stories.access.MEDIA_LINK_SECONDS", -1):
            self.assertEqual(APIClient().get(self.url).status_code, 403)

    def test_link_for_one_story_cannot_open_another(self):
        other = self.text_story()
        token = self.url.split("?t=")[1]
        self.assertEqual(APIClient().get(f"/api/v1/stories/{other.pk}/media/?t={token}").status_code, 403)

    def test_media_of_expired_story_is_gone(self):
        Story.objects.filter(pk=self.story.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(APIClient().get(self.url).status_code, 404)


class ViewsAndRepliesTests(StoryBase):
    def test_views_counted_once_and_only_author_sees_viewers(self):
        story = self.text_story()
        for _ in range(3):
            self.as_user(self.fan).post(f"/api/v1/stories/{story.pk}/view/")
        self.as_user(self.author).post(f"/api/v1/stories/{story.pk}/view/")  # own views don't count

        story.refresh_from_db()
        viewers = self.as_user(self.author).get(f"/api/v1/stories/{story.pk}/viewers/").data
        self.assertEqual(story.view_count, 1)
        self.assertEqual([v["person"]["username"] for v in viewers["viewers"]], ["fan"])
        self.assertEqual(self.as_user(self.fan).get(f"/api/v1/stories/{story.pk}/viewers/").status_code, 404)
        self.assertIsNone(self.as_user(self.fan).get(f"/api/v1/stories/{story.pk}/").data["view_count"])
        self.assertTrue(self.as_user(self.fan).get(f"/api/v1/stories/{story.pk}/").data["seen"])

    def test_strangers_cannot_mark_views(self):
        story = self.text_story()
        self.assertEqual(self.as_user(self.stranger).post(f"/api/v1/stories/{story.pk}/view/").status_code, 404)

    def test_reply_arrives_as_direct_message(self):
        story = self.text_story()
        response = self.as_user(self.fan).post(f"/api/v1/stories/{story.pk}/reply/", {"body": "Love this!"}, format="json")

        self.assertEqual(response.status_code, 201)
        message = Message.objects.get(pk=response.data["message_id"])
        self.assertEqual(message.sender, self.fan)
        self.assertIn("Love this!", message.body)
        members = set(message.conversation.memberships.values_list("user__username", flat=True))
        self.assertEqual(members, {"fan", "storyteller"})
        again = self.as_user(self.fan).post(f"/api/v1/stories/{story.pk}/reply/", {"body": "Again"}, format="json")
        self.assertEqual(again.data["conversation_id"], response.data["conversation_id"])

    def test_cannot_reply_to_own_or_invisible_story(self):
        story = self.text_story()
        self.assertEqual(self.as_user(self.author).post(f"/api/v1/stories/{story.pk}/reply/", {"body": "x"}, format="json").status_code, 400)
        self.assertEqual(self.as_user(self.stranger).post(f"/api/v1/stories/{story.pk}/reply/", {"body": "x"}, format="json").status_code, 404)

    def test_only_author_can_delete(self):
        story = self.text_story()
        self.assertEqual(self.as_user(self.fan).delete(f"/api/v1/stories/{story.pk}/").status_code, 404)
        self.assertEqual(self.as_user(self.author).delete(f"/api/v1/stories/{story.pk}/").status_code, 204)


class PurgeTests(StoryBase):
    def test_purge_deletes_expired_stories_and_files(self):
        expired = Story.objects.create(author=self.author, media_type=Story.IMAGE, expires_at=timezone.now() - timedelta(hours=1))
        expired.media.save("old.webp", ContentFile(b"x"), save=True)
        path = expired.media.name
        live = self.text_story()

        call_command("purge_expired_stories", stdout=StringIO())

        self.assertFalse(Story.objects.filter(pk=expired.pk).exists())
        self.assertTrue(Story.objects.filter(pk=live.pk).exists())
        self.assertFalse(expired.media.storage.exists(path))
