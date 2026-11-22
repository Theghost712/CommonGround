"""Query-count guards for the busiest endpoints (prevents N+1 regressions).

Seeds many posts, each with many reactions/comments/bookmarks, and checks that the
number of SQL queries per request stays flat no matter how much data exists.
"""
import time

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient, APITestCase

from apps.discussions.models import Comment, Discussion, DiscussionBookmark, DiscussionReaction
from apps.social.models import Follow
from apps.stories.models import Story

User = get_user_model()
ENDPOINTS = {
    "home feed": "/api/v1/discussions/",
    "following feed": "/api/v1/discussions/?feed=following",
    "trending": "/api/v1/discussions/trending/",
    "story tray": "/api/v1/stories/tray/",
    "people search": "/api/v1/people/?search=fan",
    "suggestions": "/api/v1/people/suggestions/",
    "profile": "/api/v1/people/author0/",
    "notifications": "/api/v1/notifications/",
}


def seed(posts=40, fans=30):
    viewer = User.objects.create_user(username="viewer", password="x")
    authors = [User.objects.create_user(username=f"author{i}", password="x") for i in range(5)]
    people = [User.objects.create_user(username=f"fan{i}", password="x") for i in range(fans)]
    for author in authors:
        Follow.objects.create(follower=viewer, following=author)
        Story.objects.create(author=author, media_type=Story.TEXT, text="hi")
    discussions = Discussion.objects.bulk_create([Discussion(author=authors[i % 5], title=f"Post {i}", body="b") for i in range(posts)])
    DiscussionReaction.objects.bulk_create([DiscussionReaction(discussion=d, user=p) for d in discussions for p in people])
    DiscussionBookmark.objects.bulk_create([DiscussionBookmark(discussion=d, user=p) for d in discussions for p in people[:10]])
    Comment.objects.bulk_create([Comment(discussion=d, author=p, body="c") for d in discussions for p in people[:10]])
    return viewer


def measure(client):
    out = {}
    for name, url in ENDPOINTS.items():
        with CaptureQueriesContext(connection) as ctx:
            started = time.perf_counter()
            response = client.get(url)
            elapsed = (time.perf_counter() - started) * 1000
        assert response.status_code == 200, (name, response.status_code)
        out[name] = (len(ctx.captured_queries), elapsed)
    return out


class QueryBudgetTests(APITestCase):
    """Fails if an endpoint starts issuing queries proportional to the data size."""

    BUDGET = 25

    def test_query_counts_do_not_grow_with_data(self):
        viewer = seed(posts=10)
        client = APIClient()
        client.force_authenticate(viewer)
        small = measure(client)
        seed_more = Discussion.objects.bulk_create([Discussion(author=User.objects.get(username="author1"), title=f"More {i}", body="b") for i in range(30)])
        fans = list(User.objects.filter(username__startswith="fan"))
        DiscussionReaction.objects.bulk_create([DiscussionReaction(discussion=d, user=p) for d in seed_more for p in fans])
        large = measure(client)
        report = "\n".join(f"  {name:<15} {small[name][0]:>3} → {large[name][0]:>3} queries   {large[name][1]:7.1f} ms" for name in ENDPOINTS)
        print("\nQueries per request (10 posts → 40 posts):\n" + report)
        for name in ENDPOINTS:
            self.assertLessEqual(large[name][0], self.BUDGET, f"{name} uses {large[name][0]} queries")
            self.assertLessEqual(large[name][0], small[name][0] + 2, f"{name} grows with data: {small[name][0]} → {large[name][0]}")


class HeavyPostTimingTests(APITestCase):
    """Popular posts (thousands of likes) must not make the feed slower."""

    def test_feed_time_does_not_depend_on_likes_per_post(self):
        viewer = User.objects.create_user(username="heavy_viewer", password="x")
        author = User.objects.create_user(username="heavy_author", password="x")
        likers = User.objects.bulk_create([User(username=f"liker{i}", password="!") for i in range(int(__import__("os").getenv("PERF_LIKES", "3000")))])
        posts = Discussion.objects.bulk_create([Discussion(author=author, title=f"Hot {i}", body="b") for i in range(20)])
        client = APIClient()
        client.force_authenticate(viewer)

        def timed(url):
            client.get(url)  # warm-up
            started = time.perf_counter()
            for _ in range(3):
                self.assertEqual(client.get(url).status_code, 200)
            return (time.perf_counter() - started) / 3 * 1000

        quiet = {name: timed(url) for name, url in [("feed", "/api/v1/discussions/"), ("trending", "/api/v1/discussions/trending/")]}
        DiscussionReaction.objects.bulk_create([DiscussionReaction(discussion=p, user=u) for p in posts for u in likers])  # 60,000 likes
        Comment.objects.bulk_create([Comment(discussion=p, author=u, body="c") for p in posts for u in likers[: len(likers) // 10]])  # 6,000 comments
        busy = {name: timed(url) for name, url in [("feed", "/api/v1/discussions/"), ("trending", "/api/v1/discussions/trending/")]}
        print("\nAverage request time, 20 posts with 0 vs 3,000 likes + 300 comments each:")
        for name in quiet:
            print(f"  {name:<9} {quiet[name]:7.1f} ms → {busy[name]:7.1f} ms")
        for name in quiet:
            self.assertLess(busy[name], max(quiet[name] * 4, 150), f"{name} slows down with popular posts")


class CursorFeedTests(APITestCase):
    def test_cursor_pages_cover_every_post_once_without_counting(self):
        viewer = User.objects.create_user(username="pager", password="x")
        author = User.objects.create_user(username="pager_author", password="x")
        Discussion.objects.bulk_create([Discussion(author=author, title=f"P{i}", body="b") for i in range(47)])
        client = APIClient()
        client.force_authenticate(viewer)
        seen, url, pages = [], "/api/v1/discussions/?paginate=cursor", 0
        while url:
            with CaptureQueriesContext(connection) as ctx:
                data = client.get(url).data
            self.assertNotIn("count", data)
            self.assertFalse(any("COUNT(*)" in q["sql"].upper() and "discussions_discussion" in q["sql"] and "GROUP BY" not in q["sql"].upper() for q in ctx.captured_queries))
            seen += [d["title"] for d in data["results"]]
            url = data["next"]
            pages += 1
        self.assertEqual(pages, 3)
        self.assertEqual(len(seen), 47)
        self.assertEqual(len(set(seen)), 47)
        self.assertEqual(seen[0], "P46")  # newest first

    def test_page_numbers_still_work_for_older_screens(self):
        viewer = User.objects.create_user(username="pager2", password="x")
        Discussion.objects.create(author=viewer, title="Only", body="b")
        client = APIClient()
        client.force_authenticate(viewer)
        self.assertEqual(client.get("/api/v1/discussions/").data["count"], 1)


class AccelRedirectTests(APITestCase):
    def test_media_is_handed_to_nginx_when_configured(self):
        from django.core.files.base import ContentFile
        from django.test import RequestFactory, override_settings

        from apps.common.media import ranged_file_response
        from apps.stories.models import Story

        author = User.objects.create_user(username="accel", password="x")
        story = Story(author=author, media_type=Story.IMAGE)
        story.media.save("a.webp", ContentFile(b"abc"), save=True)
        request = RequestFactory().get("/")
        with override_settings(MEDIA_ACCEL_REDIRECT_PREFIX="/protected-media/"):
            response = ranged_file_response(request, story.media, "image/webp")
        self.assertEqual(response["X-Accel-Redirect"], f"/protected-media/{story.media.name}")
        self.assertEqual(response.content, b"")
        direct = ranged_file_response(request, story.media, "image/webp")
        self.assertEqual(b"".join(direct.streaming_content), b"abc")
