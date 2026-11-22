from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.models import UserProfile
from apps.discussions.hashtags import extract_hashtags
from apps.discussions.models import Comment, Discussion
from apps.messaging.models import Conversation, ConversationMember, Message
from apps.notifications.models import Notification
from apps.social.models import Follow, FollowRequest
from apps.stories.models import Story

from .models import Block, Mute, Report

User = get_user_model()


def make(username, private=False):
    user = User.objects.create_user(username=username, password="Strong-pass-123", first_name=username.title())
    UserProfile.objects.update_or_create(user=user, defaults={"is_private": private})
    return user


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class BlockTests(APITestCase):
    def setUp(self):
        self.me = make("blocker")
        self.them = make("blockee")
        Follow.objects.create(follower=self.me, following=self.them)
        Follow.objects.create(follower=self.them, following=self.me)
        self.their_post = Discussion.objects.create(author=self.them, title="Their post", body="b")
        self.my_post = Discussion.objects.create(author=self.me, title="My post", body="b")
        Comment.objects.create(discussion=self.my_post, author=self.them, body="their comment")
        Story.objects.create(author=self.them, media_type=Story.TEXT, text="their story")
        self.response = client_for(self.me).put("/api/v1/safety/blocks/blockee/")

    def titles(self, user):
        return {d["title"] for d in client_for(user).get("/api/v1/discussions/").data["results"]}

    def test_block_removes_follows_both_ways(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertFalse(Follow.objects.filter(follower__in=[self.me, self.them], following__in=[self.me, self.them]).exists())

    def test_posts_comments_and_stories_disappear_both_ways(self):
        self.assertNotIn("Their post", self.titles(self.me))
        self.assertNotIn("My post", self.titles(self.them))
        comments = client_for(self.me).get(f"/api/v1/discussions/{self.my_post.id}/comments/").data
        self.assertEqual(comments, [])
        self.assertEqual(client_for(self.me).get("/api/v1/stories/user/blockee/").data, [])
        self.assertEqual(client_for(self.them).get(f"/api/v1/discussions/{self.my_post.id}/").status_code, 404)

    def test_blocker_looks_nonexistent_to_the_blocked_person(self):
        self.assertEqual(client_for(self.them).get("/api/v1/people/blocker/").status_code, 404)
        mine = client_for(self.me).get("/api/v1/people/blockee/").data
        self.assertTrue(mine["relationship"]["blocked"])

    def test_cannot_follow_or_message_across_a_block(self):
        self.assertIn(client_for(self.me).post("/api/v1/people/blockee/follow/").status_code, (403, 404))
        self.assertEqual(client_for(self.them).post("/api/v1/people/blocker/follow/").status_code, 404)
        self.assertEqual(client_for(self.them).post("/api/v1/conversations/start-direct/", {"user_id": self.me.id}, format="json").status_code, 403)

    def test_existing_direct_chat_refuses_new_messages(self):
        conversation = Conversation.objects.create(conversation_type=Conversation.DIRECT, created_by=self.them)
        ConversationMember.objects.create(conversation=conversation, user=self.them)
        ConversationMember.objects.create(conversation=conversation, user=self.me)
        response = client_for(self.them).post(f"/api/v1/conversations/{conversation.id}/messages/", {"body": "hi"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Message.objects.exists())

    def test_search_hides_blocked_people_both_ways(self):
        self.assertEqual(client_for(self.me).get("/api/v1/people/", {"search": "blockee"}).data["results"], [])
        self.assertEqual(client_for(self.them).get("/api/v1/people/", {"search": "blocker"}).data["results"], [])
        self.assertEqual(client_for(self.them).get("/api/v1/messaging/users/", {"q": "blocker"}).data["results"], [])

    def test_no_notifications_across_a_block(self):
        from apps.notifications.services import create_notification

        self.assertIsNone(create_notification(self.me, Notification.SYSTEM, "hi", actor=self.them))

    def test_unblock_restores_visibility_but_not_follows(self):
        client_for(self.me).delete("/api/v1/safety/blocks/blockee/")
        self.assertIn("Their post", self.titles(self.me))
        self.assertFalse(Follow.objects.exists())
        self.assertEqual(client_for(self.me).get("/api/v1/safety/blocks/").data, [])


class MuteTests(APITestCase):
    def setUp(self):
        self.me = make("muter")
        self.loud = make("loud")
        Follow.objects.create(follower=self.me, following=self.loud)
        Discussion.objects.create(author=self.loud, title="Loud post", body="b")
        Story.objects.create(author=self.loud, media_type=Story.TEXT, text="loud story")
        client_for(self.me).put("/api/v1/safety/mutes/loud/", {"posts": True, "stories": True}, format="json")

    def test_muted_posts_leave_feeds_but_stay_on_profile(self):
        feed = {d["title"] for d in client_for(self.me).get("/api/v1/discussions/").data["results"]}
        following = {d["title"] for d in client_for(self.me).get("/api/v1/discussions/", {"feed": "following"}).data["results"]}
        profile = {d["title"] for d in client_for(self.me).get("/api/v1/discussions/", {"author": "loud"}).data["results"]}
        self.assertNotIn("Loud post", feed | following)
        self.assertIn("Loud post", profile)

    def test_muted_stories_leave_tray_but_open_from_profile(self):
        self.assertEqual(client_for(self.me).get("/api/v1/stories/tray/").data, [])
        self.assertEqual(len(client_for(self.me).get("/api/v1/stories/user/loud/").data), 1)

    def test_mute_is_still_following_and_can_be_undone(self):
        self.assertTrue(Follow.objects.filter(follower=self.me, following=self.loud).exists())
        relation = client_for(self.me).get("/api/v1/people/loud/").data["relationship"]
        self.assertTrue(relation["muted_posts"])
        client_for(self.me).put("/api/v1/safety/mutes/loud/", {"posts": False, "stories": False}, format="json")
        self.assertFalse(Mute.objects.exists())


class ReportTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.reporter = make("reporter")
        self.author = make("poster")
        self.post = Discussion.objects.create(author=self.author, title="Spammy", body="b")

    def report(self, **data):
        return client_for(self.reporter).post("/api/v1/safety/reports/", {"target_type": "post", "target_id": self.post.id, "reason": "spam", **data}, format="json")

    def test_report_once_then_already_reported(self):
        first = self.report(details="Selling fake goods")
        second = self.report()
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertTrue(second.data["already_reported"])
        report = Report.objects.get()
        self.assertEqual((report.target_owner, report.status, report.details), (self.author, Report.OPEN, "Selling fake goods"))

    def test_cannot_report_own_or_invisible_content(self):
        own = client_for(self.author).post("/api/v1/safety/reports/", {"target_type": "post", "target_id": self.post.id, "reason": "spam"}, format="json")
        missing = self.report(target_id=999999)
        UserProfile.objects.filter(user=self.author).update(is_private=True)
        hidden = self.report()
        self.assertEqual((own.status_code, missing.status_code, hidden.status_code), (400, 400, 400))

    def test_reports_are_rate_limited(self):
        posts = [Discussion.objects.create(author=self.author, title=f"p{i}", body="b") for i in range(3)]
        with mock.patch.object(SimpleRateThrottle, "THROTTLE_RATES", {**SimpleRateThrottle.THROTTLE_RATES, "reports": "2/hour"}):
            codes = [self.report(target_id=p.id).status_code for p in posts]
        self.assertEqual(codes, [201, 201, 429])

    def test_reasons_are_validated(self):
        self.assertEqual(self.report(reason="i_dont_like_it").status_code, 400)


class PrivateAccountTests(APITestCase):
    def setUp(self):
        self.owner = make("private_owner", private=True)
        self.fan = make("hopeful_fan")
        Discussion.objects.create(author=self.owner, title="Private thoughts", body="b")
        Story.objects.create(author=self.owner, media_type=Story.TEXT, text="private story")

    def fan_sees_post(self):
        return "Private thoughts" in {d["title"] for d in client_for(self.fan).get("/api/v1/discussions/", {"author": "private_owner"}).data["results"]}

    def test_follow_becomes_a_request_and_content_stays_hidden(self):
        response = client_for(self.fan).post("/api/v1/people/private_owner/follow/")
        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.data["relationship"]["requested"])
        self.assertFalse(response.data["relationship"]["can_view"])
        self.assertFalse(Follow.objects.exists())
        self.assertTrue(Notification.objects.filter(recipient=self.owner, notification_type=Notification.FOLLOW_REQUEST).exists())
        self.assertFalse(self.fan_sees_post())
        self.assertEqual(client_for(self.fan).get("/api/v1/people/private_owner/followers/").status_code, 403)

    def test_approve_grants_access_and_notifies(self):
        client_for(self.fan).post("/api/v1/people/private_owner/follow/")
        requests = client_for(self.owner).get("/api/v1/people/requests/").data["results"]
        self.assertEqual([p["username"] for p in requests], ["hopeful_fan"])
        client_for(self.owner).post("/api/v1/people/requests/hopeful_fan/approve/")
        self.assertTrue(Follow.objects.filter(follower=self.fan, following=self.owner).exists())
        self.assertTrue(self.fan_sees_post())
        self.assertTrue(Notification.objects.filter(recipient=self.fan, notification_type=Notification.FOLLOW_ACCEPTED).exists())
        self.assertEqual(len(client_for(self.fan).get("/api/v1/stories/tray/").data), 1)

    def test_decline_and_cancel(self):
        client_for(self.fan).post("/api/v1/people/private_owner/follow/")
        client_for(self.owner).post("/api/v1/people/requests/hopeful_fan/decline/")
        self.assertFalse(FollowRequest.objects.exists() or Follow.objects.exists())
        client_for(self.fan).post("/api/v1/people/private_owner/follow/")
        client_for(self.fan).delete("/api/v1/people/private_owner/follow/")
        self.assertFalse(FollowRequest.objects.exists())

    def test_going_public_approves_waiting_requests(self):
        client_for(self.fan).post("/api/v1/people/private_owner/follow/")
        client_for(self.owner).patch("/api/v1/auth/profile/", {"is_private": False}, format="json")
        self.assertTrue(Follow.objects.filter(follower=self.fan, following=self.owner).exists())
        self.assertFalse(FollowRequest.objects.exists())

    def test_public_accounts_follow_instantly(self):
        public = make("public_person")
        self.assertEqual(client_for(self.fan).post("/api/v1/people/public_person/follow/").status_code, 201)
        self.assertTrue(Follow.objects.filter(follower=self.fan, following=public).exists())


class HashtagTests(APITestCase):
    def test_extraction(self):
        self.assertEqual(extract_hashtags("Siku njema #Arusha #arusha #maji_safi", "#2026 #a #Kilimanjaro2026 ab#notatag &#39;"), ["arusha", "maji_safi", "kilimanjaro2026"])
        self.assertEqual(extract_hashtags("#München #東京"), ["münchen", "東京"])

    def test_tag_filter_trending_and_privacy(self):
        author = make("tagger")
        hidden = make("hidden_tagger", private=True)
        viewer = make("tag_viewer")
        Discussion.objects.create(author=author, title="", body="Water day #MajiSafi #arusha")
        Discussion.objects.create(author=author, title="Again", body="#majisafi")
        Discussion.objects.create(author=hidden, title="", body="#majisafi secret")
        old = Discussion.objects.create(author=author, title="Old", body="#oldtag")
        Discussion.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=30))

        posts = client_for(viewer).get("/api/v1/discussions/", {"tag": "#MajiSafi"}).data["results"]
        trending = client_for(viewer).get("/api/v1/tags/trending/").data
        detail = client_for(viewer).get("/api/v1/tags/majisafi/").data

        self.assertEqual(len(posts), 2)
        self.assertEqual(trending[0], {"name": "majisafi", "posts": 2})
        self.assertNotIn("oldtag", [t["name"] for t in trending])
        self.assertEqual(detail, {"name": "majisafi", "posts": 2})

    def test_editing_a_post_updates_its_tags(self):
        post = Discussion.objects.create(author=make("editor"), title="", body="#first")
        post.body = "#second"
        post.save()
        self.assertEqual(list(post.hashtags.values_list("name", flat=True)), ["second"])
