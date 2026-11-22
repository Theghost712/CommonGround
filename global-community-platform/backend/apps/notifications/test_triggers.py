"""End-to-end checks that user actions create the right notifications."""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.communities.models import Community, CommunityMembership
from apps.discussions.models import Discussion

from .models import Notification, NotificationPreference

User = get_user_model()


class NotificationTriggerTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user(username="author", password="Strong-password-123")
        self.commenter = User.objects.create_user(username="commenter", password="Strong-password-123")
        self.bystander = User.objects.create_user(username="bystander", password="Strong-password-123")
        self.discussion = Discussion.objects.create(author=self.author, title="Open topic", body="Body")

    def notifications(self, user, kind=None):
        qs = Notification.objects.filter(recipient=user)
        return qs.filter(notification_type=kind) if kind else qs

    def comment(self, user, body, parent=None):
        self.client.force_authenticate(user)
        return self.client.post(
            f"/api/v1/discussions/{self.discussion.id}/comments/",
            {"body": body, "parent": parent},
            format="json",
        )

    def test_comment_notifies_discussion_author(self):
        self.comment(self.commenter, "Great point")

        notification = self.notifications(self.author, Notification.DISCUSSION_COMMENT).get()
        self.assertEqual(notification.actor, self.commenter)
        self.assertEqual(notification.target_url, f"/discussions/{self.discussion.id}")

    def test_author_commenting_on_own_discussion_creates_no_notification(self):
        self.comment(self.author, "Adding context")

        self.assertFalse(self.notifications(self.author).exists())

    def test_reply_notifies_parent_comment_author_and_discussion_author(self):
        parent_id = self.comment(self.commenter, "First").data["id"]

        self.comment(self.bystander, "Replying", parent=parent_id)

        reply_to_commenter = self.notifications(self.commenter, Notification.DISCUSSION_REPLY).get()
        self.assertIn("replied to your comment", reply_to_commenter.title)
        self.assertTrue(self.notifications(self.author, Notification.DISCUSSION_REPLY).exists())

    def test_mention_in_comment_notifies_mentioned_user(self):
        self.comment(self.commenter, "What do you think, @bystander?")

        self.assertTrue(self.notifications(self.bystander, Notification.MENTION).exists())

    def test_mention_of_unknown_user_or_email_is_ignored(self):
        self.comment(self.commenter, "Ping @nobody_here or mail me at someone@bystander.test")

        self.assertFalse(Notification.objects.filter(notification_type=Notification.MENTION).exists())

    def test_reaction_notifies_author(self):
        self.client.force_authenticate(self.commenter)

        self.client.post(f"/api/v1/discussions/{self.discussion.id}/react/", {"reaction_type": "insightful"}, format="json")

        notification = self.notifications(self.author, Notification.DISCUSSION_REACTION).get()
        self.assertEqual(notification.data["reaction_type"], "insightful")

    def test_disabled_discussion_preference_suppresses_comment_notification(self):
        NotificationPreference.objects.create(user=self.author, discussions_enabled=False)

        self.comment(self.commenter, "Muted")

        self.assertFalse(self.notifications(self.author).exists())


class PrivateCommunityMentionTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="private_owner", password="Strong-password-123")
        self.member = User.objects.create_user(username="private_member", password="Strong-password-123")
        self.outsider = User.objects.create_user(username="private_outsider", password="Strong-password-123")
        self.community = Community.objects.create(
            name="Hidden circle", description="Private", created_by=self.owner,
            visibility=Community.PRIVATE, approval_status=Community.APPROVED,
        )
        CommunityMembership.objects.create(community=self.community, user=self.owner, role=CommunityMembership.OWNER)
        CommunityMembership.objects.create(community=self.community, user=self.member)

    def test_mentions_in_private_discussion_only_reach_members(self):
        self.client.force_authenticate(self.owner)

        response = self.client.post("/api/v1/discussions/", {
            "title": "Members only",
            "body": "Hi @private_member and @private_outsider",
            "community": self.community.id,
        }, format="json")

        self.assertEqual(response.status_code, 201)
        mentions = Notification.objects.filter(notification_type=Notification.MENTION)
        self.assertEqual(list(mentions.values_list("recipient__username", flat=True)), ["private_member"])


class CommunityNotificationTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="c_owner", password="Strong-password-123")
        self.applicant = User.objects.create_user(username="c_applicant", password="Strong-password-123")
        self.member = User.objects.create_user(username="c_member", password="Strong-password-123")
        self.community = Community.objects.create(
            name="Approval club", description="Restricted", created_by=self.owner,
            visibility=Community.RESTRICTED, approval_status=Community.APPROVED,
        )
        CommunityMembership.objects.create(community=self.community, user=self.owner, role=CommunityMembership.OWNER)
        CommunityMembership.objects.create(community=self.community, user=self.member)

    def test_join_request_and_approval_notify_both_sides(self):
        self.client.force_authenticate(self.applicant)
        self.client.post(f"/api/v1/communities/{self.community.id}/join/")

        request_note = Notification.objects.get(recipient=self.owner, notification_type=Notification.COMMUNITY_MEMBERSHIP_REQUEST)
        self.assertEqual(request_note.data["applicant_id"], self.applicant.id)
        self.assertFalse(Notification.objects.filter(recipient=self.member).exists())

        membership = CommunityMembership.objects.get(community=self.community, user=self.applicant)
        self.client.force_authenticate(self.owner)
        self.client.post(f"/api/v1/communities/{self.community.id}/approve-request/", {"membership_id": membership.id}, format="json")

        self.assertTrue(
            Notification.objects.filter(recipient=self.applicant, notification_type=Notification.COMMUNITY_MEMBERSHIP_APPROVED).exists()
        )

    def test_announcement_notifies_active_members_but_not_poster(self):
        self.client.force_authenticate(self.owner)

        self.client.post(
            f"/api/v1/communities/{self.community.id}/announcements/",
            {"title": "Welcome!", "body": "Read the rules."},
            format="json",
        )

        recipients = Notification.objects.filter(notification_type=Notification.COMMUNITY_ANNOUNCEMENT)
        self.assertEqual(list(recipients.values_list("recipient__username", flat=True)), ["c_member"])
