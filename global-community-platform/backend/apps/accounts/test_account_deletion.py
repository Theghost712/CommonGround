import os
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from apps.communities.models import Community, CommunityAnnouncement, CommunityMembership
from apps.discussions.models import Discussion
from apps.events.models import CommunityEvent
from apps.messaging.models import Conversation, ConversationMember, Message
from apps.messaging.services import get_or_create_direct_conversation
from apps.stories.models import Story

User = get_user_model()
PASSWORD = "Strong-password-123"
URL = "/api/v1/auth/account/delete/"


def photo():
    buf = BytesIO()
    Image.new("RGB", (200, 200), (200, 50, 50)).save(buf, "JPEG")
    return SimpleUploadedFile("pic.jpg", buf.getvalue(), content_type="image/jpeg")


class AccountDeletionTests(APITestCase):
    def setUp(self):
        self.amina = User.objects.create_user("amina", "amina@example.com", PASSWORD)
        self.juma = User.objects.create_user("juma", "juma@example.com", PASSWORD)
        self.neema = User.objects.create_user("neema", "neema@example.com", PASSWORD)
        self.client.force_authenticate(self.amina)

    def delete(self, **data):
        payload = {"password": PASSWORD, "confirm": "DELETE", **data}
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(URL, payload, format="json")

    def test_needs_password_and_typed_confirmation(self):
        self.assertEqual(self.client.post(URL, {"password": PASSWORD}, format="json").status_code, 400)
        self.assertEqual(self.client.post(URL, {"password": "wrong", "confirm": "DELETE"}, format="json").status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.amina.pk).exists())

    def test_two_factor_code_is_required_when_on(self):
        from apps.accounts.models import TwoFactorAuth

        TwoFactorAuth.objects.create(user=self.amina, secret_encrypted="x", confirmed_at="2026-01-01T00:00:00Z")
        response = self.delete()
        self.assertEqual(response.status_code, 400)
        self.assertIn("code", response.data)
        self.assertTrue(User.objects.filter(pk=self.amina.pk).exists())

    def test_last_administrator_cannot_delete_themselves(self):
        User.objects.filter(pk=self.amina.pk).update(is_superuser=True, is_staff=True)
        self.amina.refresh_from_db()
        self.client.force_authenticate(self.amina)
        self.assertEqual(self.delete().status_code, 409)

    def test_deletes_own_content_and_hands_over_shared_things(self):
        # A community with another admin, plus an event and an announcement in it.
        community = Community.objects.create(name="Readers", slug="readers", description="x", created_by=self.amina, approval_status="approved")
        CommunityMembership.objects.update_or_create(community=community, user=self.amina, defaults={"role": CommunityMembership.OWNER})
        CommunityMembership.objects.create(community=community, user=self.neema, role=CommunityMembership.MEMBER)
        CommunityMembership.objects.create(community=community, user=self.juma, role=CommunityMembership.ADMIN)
        from datetime import timedelta

        from django.utils import timezone

        event = CommunityEvent.objects.create(community=community, created_by=self.amina, title="Meetup", description="x",
                                              starts_at=timezone.now() + timedelta(days=2), ends_at=timezone.now() + timedelta(days=2, hours=1))
        CommunityAnnouncement.objects.create(community=community, posted_by=self.amina, title="Hi", body="Welcome")
        lonely = Community.objects.create(name="Solo", slug="solo", description="x", created_by=self.amina, approval_status="approved")
        # Chats: a group she created, a direct chat, and a message.
        group = Conversation.objects.create(conversation_type=Conversation.GROUP, title="Friends", created_by=self.amina)
        for user in (self.amina, self.juma, self.neema):
            ConversationMember.objects.create(conversation=group, user=user, role=ConversationMember.OWNER if user == self.amina else ConversationMember.MEMBER)
        direct = get_or_create_direct_conversation(self.amina, self.juma)
        Message.objects.create(conversation=direct, sender=self.amina, body="hello")
        Message.objects.create(conversation=direct, sender=self.juma, body="hi back")
        # A photo post and a story with files.
        post = self.client.post("/api/v1/posts/", {"images": [photo()], "caption": "Mine"}, format="multipart")
        self.assertEqual(post.status_code, 201, post.data)
        story = self.client.post("/api/v1/stories/", {"media_type": "image", "file": photo()}, format="multipart")
        self.assertEqual(story.status_code, 201, story.data)
        story_path = Story.objects.get().media.path

        response = self.delete()
        self.assertEqual(response.status_code, 200, response.data)

        self.assertFalse(User.objects.filter(pk=self.amina.pk).exists())
        community.refresh_from_db()
        self.assertEqual(community.created_by, self.juma, "the admin takes over before plain members")
        self.assertEqual(CommunityMembership.objects.get(community=community, user=self.juma).role, CommunityMembership.OWNER)
        event.refresh_from_db()
        self.assertEqual(event.created_by, self.juma)
        self.assertFalse(CommunityAnnouncement.objects.exists())
        self.assertFalse(Community.objects.filter(pk=lonely.pk).exists(), "an empty community goes")
        group.refresh_from_db()
        self.assertEqual(group.created_by, self.juma)
        self.assertEqual(ConversationMember.objects.get(conversation=group, user=self.juma).role, ConversationMember.OWNER)
        direct.refresh_from_db()
        self.assertEqual(list(Message.objects.filter(conversation=direct).values_list("body", flat=True)), ["hi back"])
        self.assertFalse(Discussion.objects.filter(pk=post.data["id"]).exists())
        self.assertFalse(Story.objects.exists())
        self.assertFalse(os.path.exists(story_path), "uploaded files are removed too")
        # The session cookie is cleared and the old token no longer works.
        self.assertEqual(response.cookies["cg_refresh"].value, "")
        client = APIClient()
        self.assertEqual(client.post("/api/v1/auth/token/", {"username": "amina", "password": PASSWORD}, format="json").status_code, 401)
