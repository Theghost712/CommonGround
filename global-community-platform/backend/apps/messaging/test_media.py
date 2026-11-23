import os
import subprocess
import tempfile
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from apps.common.video import ffmpeg_exe
from apps.discussions.models import Discussion

from .media import purge_chat_media
from .models import Conversation, ConversationMember, Message, MessageOpen
from .services import get_or_create_direct_conversation

User = get_user_model()


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def jpeg():
    buf = BytesIO()
    Image.new("RGB", (900, 600), (200, 60, 60)).save(buf, "JPEG")
    return SimpleUploadedFile("snap.jpg", buf.getvalue(), content_type="image/jpeg")


def voice_note(seconds=1):
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "note.webm")
        subprocess.run([ffmpeg_exe(), "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}",
                        "-c:a", "libopus", path], check=True, timeout=60)
        with open(path, "rb") as handle:
            return SimpleUploadedFile("note.webm", handle.read(), content_type="audio/webm")


class ChatMediaTests(APITestCase):
    def setUp(self):
        self.amina = User.objects.create_user("amina_m", password="x")
        self.juma = User.objects.create_user("juma_m", password="x")
        self.eve = User.objects.create_user("eve_m", password="x")
        self.chat = get_or_create_direct_conversation(self.amina, self.juma)
        self.a, self.j = client_for(self.amina), client_for(self.juma)

    def send(self, client=None, **data):
        return (client or self.a).post(f"/api/v1/conversations/{self.chat.pk}/media/", data, format="multipart")

    def test_photo_message_is_reencoded_and_served_by_signed_link(self):
        response = self.send(kind="photo", file=jpeg(), caption="Look!")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual((response.data["kind"], response.data["body"]), ("photo", "Look!"))
        self.assertEqual(response.data["preview"], "📷 Photo: Look!")
        message = Message.objects.get()
        self.assertTrue(message.media.name.endswith(".webp"))
        image = APIClient().get(response.data["media_url"])
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image["Content-Type"], "image/webp")
        tampered = response.data["media_url"][:-3] + "abc"
        self.assertEqual(APIClient().get(tampered).status_code, 403)
        listed = self.j.get(f"/api/v1/conversations/{self.chat.pk}/messages/").data
        self.assertEqual(listed[-1]["kind"], "photo")

    def test_outsiders_and_blocked_people_cannot_send(self):
        self.assertEqual(self.send(client_for(self.eve), kind="photo", file=jpeg()).status_code, 403)
        self.assertEqual(self.send(kind="sticker", file=jpeg()).status_code, 400)

    def test_voice_message_is_converted_to_m4a(self):
        if ffmpeg_exe() is None:
            self.skipTest("no ffmpeg")
        response = self.send(kind="voice", file=voice_note(2))
        self.assertEqual(response.status_code, 201, response.data)
        message = Message.objects.get()
        self.assertTrue(message.media.name.endswith(".m4a"))
        self.assertAlmostEqual(message.duration_ms, 2000, delta=200)
        audio = APIClient().get(response.data["media_url"])
        self.assertEqual(audio["Content-Type"], "audio/mp4")
        self.assertEqual(self.send(kind="voice", file=SimpleUploadedFile("x.webm", b"not audio", content_type="audio/webm")).status_code, 400)

    def test_view_once_opens_once_per_recipient_then_is_deleted(self):
        response = self.send(kind="photo", file=jpeg(), view_once="true", caption="secret caption")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["media_url"], "", "no link in the message itself")
        self.assertEqual(response.data["body"], "", "captions aren't kept on view-once media")
        mid = response.data["id"]
        url = f"/api/v1/conversations/{self.chat.pk}/messages/{mid}/open/"
        self.assertEqual(self.a.post(url).status_code, 403, "the sender can't reopen it")
        opened = self.j.post(url)
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(APIClient().get(opened.data["url"]).status_code, 200)
        self.assertEqual(self.j.post(url).status_code, 410, "only once")
        message = Message.objects.get(pk=mid)
        purge_chat_media()
        self.assertTrue(Message.objects.get(pk=mid).media, "kept a few minutes so the viewer can finish loading")
        MessageOpen.objects.filter(message=message).update(opened_at=timezone.now() - timedelta(minutes=10))
        purge_chat_media()
        self.assertFalse(Message.objects.get(pk=mid).media)
        self.assertFalse(os.path.exists(message.media.path))

    def test_disappearing_messages(self):
        response = self.a.post(f"/api/v1/conversations/{self.chat.pk}/disappearing/", {"seconds": 86400}, format="json")
        self.assertEqual(response.data["disappear_seconds"], 86400)
        self.assertEqual(self.a.post(f"/api/v1/conversations/{self.chat.pk}/disappearing/", {"seconds": 5}, format="json").status_code, 400)
        notice = Message.objects.get(kind="system")
        self.assertIn("24 hours", notice.body)
        sent = self.a.post(f"/api/v1/conversations/{self.chat.pk}/messages/", {"body": "gone tomorrow"}, format="json")
        message = Message.objects.get(pk=sent.data["id"])
        self.assertAlmostEqual((message.expires_at - timezone.now()).total_seconds(), 86400, delta=10)
        Message.objects.filter(pk=message.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        bodies = [m["body"] for m in self.j.get(f"/api/v1/conversations/{self.chat.pk}/messages/").data]
        self.assertNotIn("gone tomorrow", bodies, "expired messages are hidden right away")
        purge_chat_media()
        self.assertFalse(Message.objects.filter(pk=message.pk).exists(), "and deleted by the clean-up job")

    def test_group_disappearing_needs_an_admin(self):
        group = Conversation.objects.create(conversation_type=Conversation.GROUP, title="G", created_by=self.amina)
        ConversationMember.objects.create(conversation=group, user=self.amina, role=ConversationMember.OWNER)
        ConversationMember.objects.create(conversation=group, user=self.juma)
        self.assertEqual(self.j.post(f"/api/v1/conversations/{group.pk}/disappearing/", {"seconds": 3600}, format="json").status_code, 403)
        self.assertEqual(self.a.post(f"/api/v1/conversations/{group.pk}/disappearing/", {"seconds": 3600}, format="json").status_code, 200)

    def test_unsend_removes_message_and_file(self):
        response = self.send(kind="photo", file=jpeg())
        message = Message.objects.get()
        url = f"/api/v1/conversations/{self.chat.pk}/messages/{message.pk}/"
        self.assertEqual(self.j.delete(url).status_code, 403, "only your own")
        self.assertEqual(self.a.delete(url).status_code, 204)
        self.assertFalse(os.path.exists(message.media.path))
        self.assertNotIn(message.pk, [m["id"] for m in self.j.get(f"/api/v1/conversations/{self.chat.pk}/messages/").data])

    def test_share_post_to_chat(self):
        post = Discussion.objects.create(author=self.eve, title="", body="Sunset at the beach")
        response = self.a.post(f"/api/v1/conversations/{self.chat.pk}/share-post/", {"post_id": post.pk, "caption": "look"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["shared_post"]["text"], "Sunset at the beach")
        self.assertEqual(Discussion.objects.get(pk=post.pk).share_count, 1)
        from apps.safety.models import Block

        Block.objects.create(blocker=self.eve, blocked=self.amina)
        self.assertEqual(self.a.post(f"/api/v1/conversations/{self.chat.pk}/share-post/", {"post_id": post.pk}, format="json").status_code, 400)
