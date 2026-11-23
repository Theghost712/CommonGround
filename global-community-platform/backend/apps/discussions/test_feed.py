from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.notifications.models import Notification
from apps.social.models import Follow

from .models import Discussion, DiscussionReaction, PostView

User = get_user_model()


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def post(author, body, hours_ago=1, **extra):
    item = Discussion.objects.create(author=author, title="", body=body, **extra)
    Discussion.objects.filter(pk=item.pk).update(created_at=timezone.now() - timedelta(hours=hours_ago))
    return item


class ForYouTests(APITestCase):
    def setUp(self):
        self.me = User.objects.create_user("viewer", password="x")
        self.friend = User.objects.create_user("friend", password="x")
        self.stranger = User.objects.create_user("stranger", password="x")
        self.c = client_for(self.me)

    def ids(self, **params):
        response = self.c.get("/api/v1/feed/for-you/", params)
        self.assertEqual(response.status_code, 200, response.data)
        return [item["id"] for item in response.data["results"]]

    def test_follows_engagement_and_freshness_shape_the_ranking(self):
        old = post(self.stranger, "old news", hours_ago=24 * 20)
        stranger_new = post(self.stranger, "new from a stranger", hours_ago=2)
        friend_new = post(self.friend, "new from a friend", hours_ago=2)
        Follow.objects.create(follower=self.me, following=self.friend)
        ids = self.ids()
        self.assertEqual(ids[0], friend_new.pk, "people you follow rank first")
        self.assertLess(ids.index(stranger_new.pk), ids.index(old.pk), "fresh beats stale")
        # A very popular stranger post overtakes.
        for i in range(20):
            DiscussionReaction.objects.create(discussion=stranger_new, user=User.objects.create_user(f"fan{i}", password="x"))
        self.assertEqual(self.ids()[0], stranger_new.pk)

    def test_seen_posts_sink_and_views_are_recorded(self):
        a = post(self.stranger, "first", hours_ago=1)
        b = post(self.stranger, "second", hours_ago=2)
        self.assertEqual(self.ids()[0], a.pk)
        response = self.c.post("/api/v1/feed/views/", {"views": [{"id": a.pk, "ms": 9000, "completed": True}, {"id": "junk"}]}, format="json")
        self.assertEqual(response.data["recorded"], 1)
        self.assertEqual(self.ids()[0], b.pk, "what you've watched moves down")
        self.c.post("/api/v1/feed/views/", {"views": [{"id": a.pk, "ms": 2000}]}, format="json")
        view = PostView.objects.get(user=self.me, discussion=a)
        self.assertEqual((view.watched_ms, view.completed), (9000, True), "keeps the longest watch")
        self.assertEqual(Discussion.objects.get(pk=a.pk).view_count, 1, "counted once per person")

    def test_one_query_per_page_regardless_of_size(self):
        for i in range(15):
            post(self.stranger, f"post {i}", hours_ago=i + 1)
        with CaptureQueriesContext(connection) as small:
            self.ids()
        for i in range(30):
            post(self.friend, f"more {i}", hours_ago=i + 1)
        with CaptureQueriesContext(connection) as large:
            self.ids()
        self.assertLessEqual(len(large), len(small) + 1)


class RepostTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user("creator", password="x")
        self.fan = User.objects.create_user("fan", password="x")
        self.original = post(self.author, "Original thought")

    def test_repost_counts_notifies_and_shows_original(self):
        c = client_for(self.fan)
        response = c.post(f"/api/v1/discussions/{self.original.pk}/repost/", {}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["repost_of"]["body"], "Original thought")
        self.assertEqual(Discussion.objects.get(pk=self.original.pk).share_count, 1)
        self.assertTrue(Notification.objects.filter(recipient=self.author, title__contains="reposted").exists())
        self.assertEqual(c.post(f"/api/v1/discussions/{self.original.pk}/repost/", {}, format="json").status_code, 400, "once")
        # Reposting a repost points at the original (no chains).
        quote = client_for(self.author).post(f"/api/v1/discussions/{response.data['id']}/repost/", {"comment": "thanks!"}, format="json")
        self.assertEqual(quote.data["repost_of"]["id"], self.original.pk)
        self.assertEqual(c.delete(f"/api/v1/discussions/{self.original.pk}/repost/").data["removed"], True)
        self.assertEqual(Discussion.objects.get(pk=self.original.pk).share_count, 1)


class SponsoredTests(APITestCase):
    def setUp(self):
        self.shop = User.objects.create_user("shop", password="x")
        self.me = User.objects.create_user("buyer", password="x")
        for i in range(10):
            post(User.objects.create_user(f"p{i}", password="x"), f"regular {i}", hours_ago=i + 1)
        self.ad = post(self.shop, "Big sale this week", hours_ago=200, sponsored_until=timezone.now() + timedelta(days=7),
                       sponsor_name="Shop Ltd", sponsor_url="https://shop.example.com")

    def test_one_labelled_sponsored_post_per_page_with_counts(self):
        c = client_for(self.me)
        results = c.get("/api/v1/feed/for-you/").data["results"]
        sponsored = [item for item in results if item["sponsored"]]
        self.assertEqual(len(sponsored), 1)
        self.assertEqual(sponsored[0]["sponsored"]["name"], "Shop Ltd")
        home = c.get("/api/v1/discussions/", {"paginate": "cursor"}).data["results"]
        self.assertEqual(sum(1 for item in home if item["sponsored"]), 1)
        self.assertEqual(Discussion.objects.get(pk=self.ad.pk).sponsored_impressions, 2)
        click = c.post(f"/api/v1/discussions/{self.ad.pk}/sponsored-click/")
        self.assertEqual(click.data["url"], "https://shop.example.com")
        self.assertEqual(Discussion.objects.get(pk=self.ad.pk).sponsored_clicks, 1)
        Discussion.objects.filter(pk=self.ad.pk).update(sponsored_until=timezone.now() - timedelta(minutes=1))
        self.assertFalse(any(item["sponsored"] for item in c.get("/api/v1/feed/for-you/").data["results"]))
        self.assertEqual(c.post(f"/api/v1/discussions/{self.ad.pk}/sponsored-click/").status_code, 404)


class SearchTests(APITestCase):
    def test_search_people_posts_tags_communities(self):
        me = User.objects.create_user("searcher", password="x")
        User.objects.create_user("baobab_lover", password="x", first_name="Neema")
        p = post(me, "Baobab trees in Arusha #baobab")
        from .models import Hashtag

        tag, _ = Hashtag.objects.get_or_create(name="baobab")
        p.hashtags.add(tag)
        data = client_for(me).get("/api/v1/search/", {"q": "baobab"}).data
        self.assertEqual([x["username"] for x in data["people"]], ["baobab_lover"])
        self.assertEqual([x["id"] for x in data["posts"]], [p.pk])
        self.assertEqual(data["tags"][0]["name"], "baobab")
        self.assertEqual(client_for(me).get("/api/v1/search/", {"q": "#baobab"}).data["people"], [])
        self.assertEqual(client_for(me).get("/api/v1/search/", {"q": "b"}).data["posts"], [])
