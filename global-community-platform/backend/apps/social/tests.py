from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.throttling import SimpleRateThrottle

from apps.accounts.models import UserProfile
from apps.accounts.phone import normalize_phone, phone_hash
from apps.communities.models import Community, CommunityMembership
from apps.notifications.models import Notification, NotificationPreference

from .models import ConnectionLabel, ContactMatch, Follow

User = get_user_model()


def make_user(username, first="", last="", email="", phone="", discoverable=False):
    user = User.objects.create_user(username=username, password="Strong-pass-123", first_name=first, last_name=last, email=email)
    UserProfile.objects.update_or_create(user=user, defaults={"phone_number": phone, "discoverable_by_contacts": discoverable})
    return user


class PhoneNormalizationTests(APITestCase):
    def test_formats_are_normalised_to_international_digits(self):
        for raw in ["+255 712 345 678", "0712-345-678", "00255712345678", "(0712) 345 678", "712345678"]:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_phone(raw, default_country_code="255"), "255712345678")

    def test_rejects_non_numbers(self):
        for raw in ["", "abc", "12", "+1234567890123456789"]:
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_phone(raw, default_country_code="255"))

    def test_hash_is_keyed_and_stable(self):
        self.assertEqual(phone_hash("255712345678"), phone_hash("255712345678"))
        self.assertNotEqual(phone_hash("255712345678"), phone_hash("255712345679"))
        self.assertNotIn("255712345678", phone_hash("255712345678"))


class ProfilePhoneTests(APITestCase):
    def setUp(self):
        self.user = make_user("phoney")
        self.client.force_authenticate(self.user)

    def test_profile_saves_normalised_phone_and_hash(self):
        response = self.client.patch("/api/v1/auth/profile/", {"phone_number": "0712 345 678", "discoverable_by_contacts": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["phone_number"], "255712345678")
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.phone_hash, phone_hash("255712345678"))
        self.assertTrue(profile.discoverable_by_contacts)

    def test_invalid_and_duplicate_phones_are_rejected(self):
        make_user("taken", phone="255700000001")
        self.assertEqual(self.client.patch("/api/v1/auth/profile/", {"phone_number": "abc"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch("/api/v1/auth/profile/", {"phone_number": "+255 700 000 001"}, format="json").status_code, 400)

    def test_clearing_phone_clears_hash(self):
        self.client.patch("/api/v1/auth/profile/", {"phone_number": "0712345678"}, format="json")
        self.client.patch("/api/v1/auth/profile/", {"phone_number": ""}, format="json")
        self.assertEqual(UserProfile.objects.get(user=self.user).phone_hash, "")

    def test_reserved_usernames_cannot_register(self):
        self.client.force_authenticate(None)
        token = self.client.get("/api/v1/auth/csrf/").json()["csrfToken"]
        response = self.client.post("/api/v1/auth/register/", {
            "username": "suggestions", "email": "s@example.com", "password": "Strong-pass-123",
            "password_confirm": "Strong-pass-123", "first_name": "S",
        }, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 400)
        self.assertIn("username", response.data)


class FollowTests(APITestCase):
    def setUp(self):
        self.amani = make_user("amani", "Amani", "Mushi")
        self.baraka = make_user("baraka", "Baraka", "Juma")
        self.client.force_authenticate(self.amani)

    def test_follow_is_idempotent_and_notifies_once(self):
        first = self.client.post("/api/v1/people/baraka/follow/")
        second = self.client.post("/api/v1/people/baraka/follow/")

        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertTrue(first.data["relationship"]["is_following"])
        self.assertEqual(first.data["followers_count"], 1)
        notes = Notification.objects.filter(recipient=self.baraka, notification_type=Notification.FOLLOW)
        self.assertEqual(notes.count(), 1)
        self.assertEqual(notes.get().target_url, "/u/amani")

    def test_follow_notification_respects_preference(self):
        NotificationPreference.objects.update_or_create(user=self.baraka, defaults={"social_enabled": False})
        self.client.post("/api/v1/people/baraka/follow/")
        self.assertFalse(Notification.objects.filter(recipient=self.baraka).exists())

    def test_unfollow(self):
        self.client.post("/api/v1/people/baraka/follow/")
        response = self.client.delete("/api/v1/people/baraka/follow/")
        self.assertFalse(response.data["relationship"]["is_following"])
        self.assertFalse(Follow.objects.exists())

    def test_cannot_follow_self_or_unknown(self):
        self.assertEqual(self.client.post("/api/v1/people/amani/follow/").status_code, 400)
        self.assertEqual(self.client.post("/api/v1/people/ghost/follow/").status_code, 404)

    def test_mutual_and_follows_you_relationship(self):
        Follow.objects.create(follower=self.baraka, following=self.amani)
        before = self.client.get("/api/v1/people/baraka/").data["relationship"]
        self.client.post("/api/v1/people/baraka/follow/")
        after = self.client.get("/api/v1/people/baraka/").data["relationship"]

        self.assertEqual((before["follows_you"], before["is_mutual"]), (True, False))
        self.assertTrue(after["is_mutual"])

    def test_followers_and_following_lists(self):
        carol = make_user("carol")
        Follow.objects.create(follower=self.baraka, following=carol)
        Follow.objects.create(follower=self.amani, following=carol)

        followers = self.client.get("/api/v1/people/carol/followers/").data["results"]
        following = self.client.get("/api/v1/people/amani/following/").data["results"]

        self.assertEqual({p["username"] for p in followers}, {"amani", "baraka"})
        self.assertEqual([p["username"] for p in following], ["carol"])

    def test_mutual_followers_preview(self):
        carol = make_user("carol")
        Follow.objects.create(follower=self.amani, following=carol)
        Follow.objects.create(follower=carol, following=self.baraka)

        relation = self.client.get("/api/v1/people/baraka/").data["relationship"]

        self.assertEqual(relation["mutual_followers_count"], 1)
        self.assertEqual(relation["mutual_followers_preview"], ["carol"])

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/v1/people/baraka/").status_code, 401)


class ProfileAndSearchTests(APITestCase):
    def setUp(self):
        self.viewer = make_user("viewer")
        self.target = make_user("neema", "Neema", "Kileo", email="neema@example.com", phone="255711111111")
        self.client.force_authenticate(self.viewer)

    def test_profile_never_exposes_contact_details(self):
        data = self.client.get("/api/v1/people/neema/").data
        flat = str(data)
        self.assertNotIn("neema@example.com", flat)
        self.assertNotIn("255711111111", flat)
        self.assertNotIn("phone", flat)
        self.assertEqual(data["display_name"], "Neema Kileo")
        self.assertIn("discussions_count", data)

    def test_search_by_name_and_username_but_not_email_or_phone(self):
        by_first = self.client.get("/api/v1/people/", {"search": "neema"}).data["results"]
        by_full = self.client.get("/api/v1/people/", {"search": "Neema Kil"}).data["results"]
        by_email = self.client.get("/api/v1/people/", {"search": "example.com"}).data["results"]
        by_phone = self.client.get("/api/v1/people/", {"search": "2557111"}).data["results"]
        self.assertEqual([p["username"] for p in by_first], ["neema"])
        self.assertEqual([p["username"] for p in by_full], ["neema"])
        self.assertEqual((by_email, by_phone), ([], []))

    def test_search_needs_two_characters_and_excludes_self(self):
        self.assertEqual(self.client.get("/api/v1/people/", {"search": "n"}).data["results"], [])
        self.assertEqual(self.client.get("/api/v1/people/", {"search": "viewer"}).data["results"], [])

    def test_private_label_set_and_cleared(self):
        response = self.client.put("/api/v1/people/neema/label/", {"label": "family"}, format="json")
        self.assertEqual(response.data, {"label": "family"})
        self.assertEqual(self.client.get("/api/v1/people/neema/").data["relationship"]["label"], "family")

        # Labels are private: Neema does not see the viewer's label.
        self.client.force_authenticate(self.target)
        self.assertIsNone(self.client.get("/api/v1/people/viewer/").data["relationship"]["label"])

        self.client.force_authenticate(self.viewer)
        self.client.delete("/api/v1/people/neema/label/")
        self.assertFalse(ConnectionLabel.objects.exists())

    def test_invalid_label_rejected(self):
        self.assertEqual(self.client.put("/api/v1/people/neema/label/", {"label": "enemy"}, format="json").status_code, 400)

    def test_author_filter_on_discussions(self):
        from apps.discussions.models import Discussion

        Discussion.objects.create(author=self.target, title="By Neema", body="x")
        Discussion.objects.create(author=self.viewer, title="By viewer", body="y")
        titles = [d["title"] for d in self.client.get("/api/v1/discussions/", {"author": "neema"}).data["results"]]
        self.assertEqual(titles, ["By Neema"])
        self.assertEqual(self.client.get("/api/v1/people/neema/").data["discussions_count"], 1)


class ContactMatchTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.me = make_user("me_user")
        self.found = make_user("found", phone="255722222222", discoverable=True, email="Found@Example.com")
        self.hidden = make_user("hidden", phone="255733333333", discoverable=False, email="hidden@example.com")
        self.client.force_authenticate(self.me)

    def test_matches_only_opted_in_members_by_phone_or_email(self):
        response = self.client.post("/api/v1/people/contacts/match/", {
            "phones": ["0722 222 222", "0733 333 333", "not-a-number"],
            "emails": ["found@example.com", "hidden@example.com"],
        }, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([p["username"] for p in response.data["matches"]], ["found"])
        self.assertTrue(response.data["matches"][0]["relationship"]["in_contacts"])
        self.assertTrue(ContactMatch.objects.filter(owner=self.me, target=self.found).exists())
        self.assertFalse(ContactMatch.objects.filter(target=self.hidden).exists())

    def test_matched_contacts_show_in_suggestions(self):
        self.client.post("/api/v1/people/contacts/match/", {"phones": ["+255722222222"]}, format="json")
        suggestions = self.client.get("/api/v1/people/suggestions/").data
        self.assertEqual(suggestions[0]["username"], "found")
        self.assertEqual(suggestions[0]["reason"], "In your contacts")

    def test_request_limits(self):
        self.assertEqual(self.client.post("/api/v1/people/contacts/match/", {}, format="json").status_code, 400)
        too_many = {"phones": [f"07{i:08d}" for i in range(2001)]}
        self.assertEqual(self.client.post("/api/v1/people/contacts/match/", too_many, format="json").status_code, 400)

    def test_contact_matching_is_rate_limited(self):
        rates = {**SimpleRateThrottle.THROTTLE_RATES, "contacts": "2/hour"}
        with mock.patch.object(SimpleRateThrottle, "THROTTLE_RATES", rates):
            codes = [self.client.post("/api/v1/people/contacts/match/", {"phones": ["0722222222"]}, format="json").status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])


class SuggestionTests(APITestCase):
    def setUp(self):
        self.me = make_user("me_user")
        self.friend = make_user("friend")
        self.fof = make_user("fof")
        self.fan = make_user("fan")
        self.neighbour = make_user("neighbour")
        Follow.objects.create(follower=self.me, following=self.friend)
        Follow.objects.create(follower=self.friend, following=self.fof)
        Follow.objects.create(follower=self.fan, following=self.me)
        community = Community.objects.create(name="Village", description="d", created_by=self.me, approval_status=Community.APPROVED)
        for user in (self.me, self.neighbour):
            CommunityMembership.objects.create(community=community, user=user, status=CommunityMembership.ACTIVE)
        self.client.force_authenticate(self.me)

    def test_suggestions_rank_reasons_and_skip_people_already_followed(self):
        data = self.client.get("/api/v1/people/suggestions/").data
        reasons = {p["username"]: p["reason"] for p in data}

        self.assertEqual(reasons["fan"], "Follows you")
        self.assertEqual(reasons["fof"], "Followed by 1 person you follow")
        self.assertEqual(reasons["neighbour"], "Also in Village")
        self.assertNotIn("friend", reasons)
        self.assertNotIn("me_user", reasons)
        self.assertEqual([p["username"] for p in data][:2], ["fan", "fof"])


class NotificationPreferenceFieldsTests(APITestCase):
    def test_sound_and_popup_preferences_round_trip(self):
        user = make_user("prefs")
        self.client.force_authenticate(user)
        response = self.client.patch("/api/v1/notifications/preferences/", {"sound_enabled": False, "popup_enabled": False, "social_enabled": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data["sound_enabled"], response.data["popup_enabled"], response.data["social_enabled"]), (False, False, False))


class HomeFeedTests(APITestCase):
    def setUp(self):
        from apps.discussions.models import Discussion

        self.me = make_user("feed_me", "Feed", "Me")
        self.friend = make_user("feed_friend", "Asha", "Juma")
        self.quiet = make_user("feed_quiet")
        self.stranger = make_user("feed_stranger")
        UserProfile.objects.filter(user=self.friend).update(avatar_url="https://example.com/asha.jpg")
        Follow.objects.create(follower=self.me, following=self.friend)
        Follow.objects.create(follower=self.me, following=self.quiet)
        self.mine = Discussion.objects.create(author=self.me, title="Mine", body="x")
        self.friends = Discussion.objects.create(author=self.friend, title="Friend's", body="y")
        self.strangers = Discussion.objects.create(author=self.stranger, title="Stranger's", body="z")
        self.client.force_authenticate(self.me)

    def test_following_feed_shows_followed_people_and_self_only(self):
        titles = {d["title"] for d in self.client.get("/api/v1/discussions/", {"feed": "following"}).data["results"]}
        everyone = {d["title"] for d in self.client.get("/api/v1/discussions/").data["results"]}
        self.assertEqual(titles, {"Mine", "Friend's"})
        self.assertEqual(everyone, {"Mine", "Friend's", "Stranger's"})

    def test_posts_carry_author_name_and_avatar(self):
        post = self.client.get(f"/api/v1/discussions/{self.friends.id}/").data
        self.assertEqual(post["author_display_name"], "Asha Juma")
        self.assertEqual(post["author_avatar_url"], "https://example.com/asha.jpg")

    def test_following_feed_needs_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/v1/discussions/", {"feed": "following"}).data["results"], [])

    def test_stories_list_followed_people_recent_first_with_new_flag(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.discussions.models import Discussion

        old = Discussion.objects.create(author=self.quiet, title="Old", body="o")
        Discussion.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=3))

        stories = self.client.get("/api/v1/people/stories/").data

        self.assertEqual([s["username"] for s in stories], ["feed_friend", "feed_quiet"])
        self.assertTrue(stories[0]["has_new"])
        self.assertEqual(stories[0]["latest_discussion_id"], self.friends.id)
        self.assertFalse(stories[1]["has_new"])
        self.assertNotIn("feed_stranger", [s["username"] for s in stories])

    def test_stories_skip_posts_the_viewer_cannot_see(self):
        from apps.discussions.models import Discussion

        private = Community.objects.create(name="Secret", description="d", created_by=self.friend, visibility=Community.PRIVATE, approval_status=Community.APPROVED)
        Discussion.objects.filter(pk=self.friends.pk).update(community=private)

        story = next(s for s in self.client.get("/api/v1/people/stories/").data if s["username"] == "feed_friend")

        self.assertIsNone(story["latest_discussion_id"])
        self.assertFalse(story["has_new"])
