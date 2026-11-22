from datetime import timedelta
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from apps.communities.models import Community, CommunityMembership
from apps.discussions.models import Comment, Discussion, DiscussionAttachment
from apps.notifications.models import Notification
from apps.safety.models import Report

from .models import ModerationAction

User = get_user_model()
PASSWORD = "Strong-pass-123"


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class ModerationTestBase(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user("mod_staff", password=PASSWORD, is_staff=True)
        self.author = User.objects.create_user("troll", "troll@example.com", PASSWORD)
        self.reporter = User.objects.create_user("reporter", password=PASSWORD)
        self.reporter2 = User.objects.create_user("reporter2", password=PASSWORD)
        self.nobody = User.objects.create_user("nobody", password=PASSWORD)
        self.post = Discussion.objects.create(author=self.author, title="Buy cheap followers", body="spam spam")

    def report(self, reporter, target_type="post", target_id=None, reason="spam", details=""):
        response = client_for(reporter).post("/api/v1/safety/reports/", {
            "target_type": target_type, "target_id": target_id or self.post.pk, "reason": reason, "details": details,
        }, format="json")
        assert response.status_code in (200, 201), response.data
        return response

    def decide(self, client, **data):
        payload = {"target_type": "post", "target_id": self.post.pk, **data}
        return client.post("/api/v1/moderation/decisions/", payload, format="json")


class QueueTests(ModerationTestBase):
    def test_only_moderators_can_open_the_queue(self):
        self.assertEqual(client_for(self.nobody).get("/api/v1/moderation/queue/").status_code, 403)
        self.assertEqual(APIClient().get("/api/v1/moderation/queue/").status_code, 401)
        me = client_for(self.nobody).get("/api/v1/auth/me/").data
        self.assertFalse(me["can_moderate"])
        self.assertTrue(client_for(self.staff).get("/api/v1/auth/me/").data["can_moderate"])

    def test_reports_are_grouped_by_target_with_reasons_and_details(self):
        self.report(self.reporter, details="Selling followers")
        self.report(self.reporter2, reason="scam")
        other = Discussion.objects.create(author=self.author, title="Other", body="x")
        self.report(self.reporter, target_id=other.pk)
        queue = client_for(self.staff).get("/api/v1/moderation/queue/").data
        self.assertEqual(queue["count"], 2)
        first = queue["results"][0]
        self.assertEqual((first["target_id"], first["report_count"]), (self.post.pk, 2))
        self.assertEqual({r["reason"] for r in first["reasons"]}, {"spam", "scam"})
        self.assertEqual(first["details"], ["Selling followers"])
        self.assertEqual(first["owner"]["username"], "troll")
        self.assertIn("Buy cheap followers", first["preview"]["text"])
        self.assertEqual(first["preview"]["url"], f"/discussions/{self.post.pk}")


class DecisionTests(ModerationTestBase):
    def test_dismiss_closes_reports_and_tells_reporters(self):
        self.report(self.reporter)
        response = self.decide(client_for(self.staff), action="dismiss")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["reports_closed"], 1)
        self.assertTrue(Discussion.objects.filter(pk=self.post.pk).exists())
        self.assertEqual(Report.objects.get().status, Report.DISMISSED)
        note = Notification.objects.get(recipient=self.reporter)
        self.assertIn("didn't find a violation", note.body)
        self.assertEqual(client_for(self.staff).get("/api/v1/moderation/queue/").data["count"], 0)

    def test_remove_deletes_content_keeps_snapshot_and_notifies(self):
        self.report(self.reporter)
        self.report(self.reporter2)
        self.assertEqual(self.decide(client_for(self.staff), action="remove", reason="").status_code, 400, "reason required")
        response = self.decide(client_for(self.staff), action="remove", reason="Spam and fake engagement")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(Discussion.objects.filter(pk=self.post.pk).exists())
        log = ModerationAction.objects.get()
        self.assertEqual(log.action, ModerationAction.REMOVE)
        self.assertEqual(log.reports_closed, 2)
        self.assertIn("Buy cheap followers", log.snapshot["text"])
        self.assertEqual(log.snapshot["owner"], "troll")
        self.assertIn("Spam and fake engagement", Notification.objects.get(recipient=self.author).body)
        self.assertEqual(Notification.objects.filter(recipient__in=[self.reporter, self.reporter2]).count(), 2)
        self.assertEqual(Report.objects.filter(status=Report.ACTIONED).count(), 2)

    def test_suspend_blocks_sign_in_and_ends_sessions_then_restore(self):
        session = APIClient()
        login = session.post("/api/v1/auth/token/", {"username": "troll", "password": PASSWORD}, format="json")
        session.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        from unittest import mock

        from rest_framework_simplejwt.utils import aware_utcnow

        self.report(self.reporter, target_type="user", target_id=self.author.pk, reason="harassment")
        staff = client_for(self.staff)
        self.assertEqual(self.decide(staff, target_type="user", target_id=self.author.pk, action="suspend", reason="Harassment").status_code, 400, "days required")
        # Revocation counts whole seconds; make the existing session older than it.
        with mock.patch("apps.accounts.security.timezone.now", return_value=timezone.now() + timedelta(seconds=2)):
            response = self.decide(staff, target_type="user", target_id=self.author.pk, action="suspend", reason="Harassment", days=7)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(session.get("/api/v1/auth/me/").status_code, 401)
        refused = APIClient().post("/api/v1/auth/token/", {"username": "troll", "password": PASSWORD}, format="json")
        self.assertEqual(refused.status_code, 403)
        self.assertIn("suspended until", refused.data["detail"])
        self.assertIn("Harassment", refused.data["detail"])
        wrong = APIClient().post("/api/v1/auth/token/", {"username": "troll", "password": "wrong"}, format="json")
        self.assertEqual(wrong.status_code, 401, "a wrong password reveals nothing about the suspension")

        record = staff.get("/api/v1/moderation/accounts/troll/").data
        self.assertIsNotNone(record["user"]["suspended_until"])
        self.assertEqual(record["history"][0]["action"], "suspend")
        restored = staff.post("/api/v1/moderation/accounts/troll/restore/", {"reason": "Appeal accepted"}, format="json")
        self.assertEqual(restored.status_code, 200, restored.data)
        self.assertEqual(APIClient().post("/api/v1/auth/token/", {"username": "troll", "password": PASSWORD}, format="json").status_code, 200)

    def test_ban_deactivates_and_can_remove_content(self):
        self.report(self.reporter)
        response = self.decide(client_for(self.staff), action="ban", reason="Spam network", remove_content=True)
        self.assertEqual(response.status_code, 201, response.data)
        self.author.refresh_from_db()
        self.assertFalse(self.author.is_active)
        self.assertFalse(Discussion.objects.filter(pk=self.post.pk).exists())
        self.assertEqual(APIClient().post("/api/v1/auth/token/", {"username": "troll", "password": PASSWORD}, format="json").status_code, 401)

    def test_warn_sends_a_notice(self):
        self.report(self.reporter)
        self.assertEqual(self.decide(client_for(self.staff), action="warn", reason="Please stop posting ads").status_code, 201)
        self.assertTrue(Discussion.objects.filter(pk=self.post.pk).exists())
        self.assertIn("warning", Notification.objects.get(recipient=self.author).body)

    def test_guards(self):
        staff = client_for(self.staff)
        own = Discussion.objects.create(author=self.staff, title="Mine", body="x")
        self.assertEqual(self.decide(staff, target_id=own.pk, action="remove", reason="x").status_code, 400)
        other_staff = User.objects.create_user("staff2", password=PASSWORD, is_staff=True)
        self.assertEqual(self.decide(staff, target_type="user", target_id=other_staff.pk, action="ban", reason="x").status_code, 400)
        self.assertEqual(self.decide(staff, target_type="user", target_id=self.author.pk, action="remove", reason="x").status_code, 400)
        self.assertEqual(self.decide(client_for(self.nobody), action="remove", reason="x").status_code, 403)

    def test_already_deleted_target_still_closes_reports(self):
        self.report(self.reporter)
        post_id = self.post.pk
        self.post.delete()
        response = self.decide(client_for(self.staff), target_id=post_id, action="dismiss")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Report.objects.get().status, Report.DISMISSED)


class CommunityModeratorTests(ModerationTestBase):
    def setUp(self):
        super().setUp()
        self.community = Community.objects.create(name="Arusha Tech", description="d", created_by=self.staff, approval_status=Community.APPROVED)
        self.mod = User.objects.create_user("community_mod", password=PASSWORD)
        CommunityMembership.objects.create(community=self.community, user=self.mod, role=CommunityMembership.MODERATOR, status=CommunityMembership.ACTIVE)
        CommunityMembership.objects.create(community=self.community, user=self.author, role=CommunityMembership.MEMBER, status=CommunityMembership.ACTIVE)
        self.in_community = Discussion.objects.create(author=self.author, community=self.community, title="Off-topic ad", body="buy")
        self.comment = Comment.objects.create(discussion=self.in_community, author=self.author, body="rude comment")

    def test_sees_only_their_communities_and_can_remove_there(self):
        self.report(self.reporter)  # open post outside the community
        self.report(self.reporter, target_id=self.in_community.pk)
        self.report(self.reporter, target_type="comment", target_id=self.comment.pk, reason="harassment")
        mod = client_for(self.mod)
        self.assertTrue(mod.get("/api/v1/auth/me/").data["can_moderate"])
        queue = mod.get("/api/v1/moderation/queue/").data["results"]
        self.assertEqual({(i["target_type"], i["target_id"]) for i in queue}, {("post", self.in_community.pk), ("comment", self.comment.pk)})
        self.assertFalse(queue[0]["can_enforce"])

        self.assertEqual(self.decide(mod, target_type="comment", target_id=self.comment.pk, action="remove", reason="Be kind").status_code, 201)
        self.assertFalse(Comment.objects.filter(pk=self.comment.pk).exists())
        self.assertEqual(self.decide(mod, action="remove", reason="x").status_code, 400, "post outside their community")
        self.assertEqual(self.decide(mod, target_id=self.in_community.pk, action="suspend", reason="x", days=3).status_code, 400)
        self.assertEqual(self.decide(mod, target_id=self.in_community.pk, action="warn", reason="x").status_code, 400)
        self.assertEqual(mod.get("/api/v1/moderation/accounts/troll/").status_code, 403)
        log = mod.get("/api/v1/moderation/log/").data
        self.assertEqual([row["action"] for row in log], ["remove"])


class AttachmentFileCleanupTests(TestCase):
    def test_deleting_a_post_deletes_its_files(self):
        author = User.objects.create_user("photog", password=PASSWORD)
        client = client_for(author)
        buf = BytesIO()
        Image.new("RGB", (800, 600), (10, 20, 30)).save(buf, "JPEG")
        with self.captureOnCommitCallbacks(execute=True):
            created = client.post("/api/v1/posts/", {"images": [SimpleUploadedFile("a.jpg", buf.getvalue(), content_type="image/jpeg")]}, format="multipart")
        self.assertEqual(created.status_code, 201, created.data)
        attachment = DiscussionAttachment.objects.get()
        paths = [Path(settings.MEDIA_ROOT) / name for name in {attachment.display.name, attachment.thumbnail.name}]
        self.assertTrue(all(path.exists() for path in paths))
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(client.delete(f"/api/v1/discussions/{created.data['id']}/").status_code, 204)
        self.assertFalse(any(path.exists() for path in paths))
