from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import UserProfile
from apps.notifications.models import Notification
from apps.safety.models import Block

from .models import Follow, FollowRequest

User = get_user_model()
PASSWORD = "Strong-pass-123"


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class DiscoverTests(APITestCase):
    def setUp(self):
        self.me = User.objects.create_user("me_user", password=PASSWORD)
        self.star = User.objects.create_user("star", password=PASSWORD)
        self.fan1 = User.objects.create_user("fan1", password=PASSWORD)
        self.fan2 = User.objects.create_user("fan2", password=PASSWORD)
        self.newbie = User.objects.create_user("newbie", password=PASSWORD)
        self.hidden = User.objects.create_user("hidden", password=PASSWORD, is_active=False)
        self.blocker = User.objects.create_user("blocker", password=PASSWORD)
        for fan in (self.fan1, self.fan2):
            Follow.objects.create(follower=fan, following=self.star)
        Block.objects.create(blocker=self.blocker, blocked=self.me)

    def usernames(self, response):
        return [p["username"] for p in response.data["results"]]

    def test_everyone_is_listed_popular_first_or_newest_first(self):
        popular = client_for(self.me).get("/api/v1/people/discover/")
        self.assertEqual(popular.status_code, 200)
        names = self.usernames(popular)
        self.assertEqual(names[0], "star")
        self.assertNotIn("me_user", names)
        self.assertNotIn("hidden", names, "inactive accounts are not listed")
        self.assertNotIn("blocker", names, "blocked in either direction is not listed")
        self.assertEqual(set(names), {"star", "fan1", "fan2", "newbie"})
        newest = self.usernames(client_for(self.me).get("/api/v1/people/discover/?sort=new"))
        self.assertEqual(newest[0], "newbie")
        self.assertEqual(APIClient().get("/api/v1/people/discover/").status_code, 401)

    def test_new_members_get_popular_and_new_suggestions_instead_of_nothing(self):
        suggestions = client_for(self.me).get("/api/v1/people/suggestions/").data
        names = [p["username"] for p in suggestions]
        self.assertEqual(names[0], "star")
        self.assertEqual(suggestions[0]["reason"], "Popular on CommonGround")
        self.assertIn("New to CommonGround", {p["reason"] for p in suggestions})
        self.assertNotIn("blocker", names)
        self.assertNotIn("me_user", names)

    def test_real_reasons_still_win(self):
        Follow.objects.create(follower=self.newbie, following=self.me)
        suggestions = client_for(self.me).get("/api/v1/people/suggestions/").data
        self.assertEqual((suggestions[0]["username"], suggestions[0]["reason"]), ("newbie", "Follows you"))

    def test_discover_and_invite_are_reserved_usernames(self):
        for name in ("discover", "invite"):
            response = APIClient().post("/api/v1/auth/register/", {
                "username": name, "email": f"{name}@example.com", "password": PASSWORD, "password_confirm": PASSWORD,
            }, format="json")
            self.assertEqual(response.status_code, 400, name)


class PickedContactsTests(APITestCase):
    def setUp(self):
        self.me = User.objects.create_user("picker", password=PASSWORD)
        self.friend = User.objects.create_user("friend", "friend@example.com", PASSWORD)
        UserProfile.objects.update_or_create(user=self.friend, defaults={"phone_number": "255712000111", "discoverable_by_contacts": True})
        self.shy = User.objects.create_user("shy", "shy@example.com", PASSWORD)
        UserProfile.objects.update_or_create(user=self.shy, defaults={"phone_number": "255712000222", "discoverable_by_contacts": False})

    def test_each_picked_contact_is_either_a_member_or_invitable(self):
        response = client_for(self.me).post("/api/v1/people/contacts/match/", {"contacts": [
            {"key": "c1", "phones": ["0712 000 111"]},           # findable member (local format)
            {"key": "c2", "phones": ["+255 712 000 222"]},       # member who is not findable
            {"key": "c3", "emails": ["FRIEND@example.com"]},     # same member by email
            {"key": "c4", "phones": ["+255 700 999 999"], "emails": ["mama@example.com"]},  # not a member
        ]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        by_key = {c["key"]: c["user_id"] for c in response.data["contacts"]}
        self.assertEqual(by_key, {"c1": self.friend.pk, "c2": None, "c3": self.friend.pk, "c4": None})
        self.assertEqual([p["username"] for p in response.data["matches"]], ["friend"])

    def test_old_phones_and_emails_format_still_works(self):
        response = client_for(self.me).post("/api/v1/people/contacts/match/", {"phones": ["0712000111"]}, format="json")
        self.assertEqual([p["username"] for p in response.data["matches"]], ["friend"])
        self.assertEqual(response.data["contacts"], [])

    def test_blocked_members_are_not_revealed(self):
        Block.objects.create(blocker=self.friend, blocked=self.me)
        response = client_for(self.me).post("/api/v1/people/contacts/match/", {"contacts": [{"key": "c1", "phones": ["0712000111"]}]}, format="json")
        self.assertEqual(response.data["contacts"], [{"key": "c1", "user_id": None}])
        self.assertEqual(response.data["matches"], [])


class InviteTests(APITestCase):
    def register(self, invited_by=None, username="joiner"):
        data = {"username": username, "email": f"{username}@example.com", "password": PASSWORD, "password_confirm": PASSWORD, "first_name": "Joy"}
        if invited_by is not None:
            data["invited_by"] = invited_by
        return APIClient().post("/api/v1/auth/register/", data, format="json")

    def test_joining_from_an_invite_connects_both_people_and_tells_the_inviter(self):
        inviter = User.objects.create_user("asha", password=PASSWORD)
        self.assertEqual(self.register("@Asha").status_code, 201)
        joiner = User.objects.get(username="joiner")
        self.assertTrue(Follow.objects.filter(follower=joiner, following=inviter).exists())
        self.assertTrue(Follow.objects.filter(follower=inviter, following=joiner).exists())
        note = Notification.objects.filter(recipient=inviter, title__contains="joined CommonGround from your invite").get()
        self.assertEqual(note.target_url, "/u/joiner")

    def test_private_inviter_gets_a_follow_request_instead(self):
        inviter = User.objects.create_user("private_pat", password=PASSWORD)
        UserProfile.objects.update_or_create(user=inviter, defaults={"is_private": True})
        self.assertEqual(self.register("private_pat").status_code, 201)
        joiner = User.objects.get(username="joiner")
        self.assertTrue(FollowRequest.objects.filter(requester=joiner, target=inviter).exists())
        self.assertFalse(Follow.objects.filter(follower=joiner, following=inviter).exists())

    def test_unknown_or_blank_inviter_never_breaks_sign_up(self):
        self.assertEqual(self.register("nobody_here").status_code, 201)
        self.assertEqual(self.register("", username="joiner2").status_code, 201)
        self.assertEqual(Follow.objects.count(), 0)
