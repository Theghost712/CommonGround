from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from apps.safety.models import Block

from .models import Discussion, DiscussionAttachment, Poll, PollVote

User = get_user_model()


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class PollTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user("pollster", password="x")
        self.voter = User.objects.create_user("voter", password="x")
        self.other = User.objects.create_user("other", password="x")
        self.a, self.v, self.o = client_for(self.author), client_for(self.voter), client_for(self.other)

    def create(self, **extra):
        data = {"question": "Best time to meet?", "options": ["Morning", "Afternoon", "Evening"], "duration_hours": 24, **extra}
        return self.a.post("/api/v1/posts/poll/", data, format="json")

    def test_create_and_vote_hides_results_until_voting(self):
        created = self.create(caption="Help me plan #meetup")
        self.assertEqual(created.status_code, 201, created.data)
        poll = created.data["poll"]
        self.assertEqual([o["text"] for o in poll["options"]], ["Morning", "Afternoon", "Evening"])
        self.assertTrue(poll["results_visible"], "author always sees results")
        post_id = created.data["id"]

        before = self.v.get(f"/api/v1/discussions/{post_id}/").data["poll"]
        self.assertFalse(before["results_visible"])
        self.assertIsNone(before["options"][0]["votes"])

        evening = poll["options"][2]["id"]
        voted = self.v.post(f"/api/v1/discussions/{post_id}/vote/", {"option_ids": [evening]}, format="json")
        self.assertEqual(voted.status_code, 200, voted.data)
        self.assertEqual(voted.data["my_votes"], [evening])
        self.assertEqual(voted.data["options"][2]["votes"], 1)
        self.assertEqual(voted.data["options"][2]["percent"], 100)
        self.assertEqual(voted.data["total_voters"], 1)

        # Changing the vote replaces it; taking it back removes it.
        morning = poll["options"][0]["id"]
        changed = self.v.post(f"/api/v1/discussions/{post_id}/vote/", {"option_ids": [morning]}, format="json")
        self.assertEqual(changed.data["my_votes"], [morning])
        self.assertEqual(PollVote.objects.filter(user=self.voter).count(), 1)
        removed = self.v.delete(f"/api/v1/discussions/{post_id}/vote/")
        self.assertEqual(removed.data["my_votes"], [])
        self.assertFalse(removed.data["results_visible"])

    def test_single_choice_multi_choice_and_bad_options(self):
        single = self.create().data
        url = f"/api/v1/discussions/{single['id']}/vote/"
        ids = [o["id"] for o in single["poll"]["options"]]
        self.assertEqual(self.v.post(url, {"option_ids": ids[:2]}, format="json").status_code, 400)
        self.assertEqual(self.v.post(url, {"option_ids": []}, format="json").status_code, 400)
        self.assertEqual(self.v.post(url, {"option_ids": ["x"]}, format="json").status_code, 400)
        other_poll = self.create().data
        self.assertEqual(self.v.post(url, {"option_ids": [other_poll["poll"]["options"][0]["id"]]}, format="json").status_code, 400)

        multi = self.create(allows_multiple=True).data
        mids = [o["id"] for o in multi["poll"]["options"]]
        murl = f"/api/v1/discussions/{multi['id']}/vote/"
        self.assertEqual(self.v.post(murl, {"option_ids": mids[:2]}, format="json").status_code, 200)
        result = self.o.post(murl, {"option_ids": [mids[0]]}, format="json").data
        self.assertEqual(result["total_voters"], 2, "voters, not votes")
        self.assertEqual(result["options"][0]["percent"], 100)
        self.assertEqual(result["options"][1]["percent"], 50)

    def test_validation(self):
        self.assertEqual(self.create(options=["Only one"]).status_code, 400)
        self.assertEqual(self.create(options=["Same", "same"]).status_code, 400)
        self.assertEqual(self.create(options=[str(i) for i in range(7)]).status_code, 400)
        self.assertEqual(self.create(duration_hours=0).status_code, 400)
        self.assertEqual(self.create(duration_hours=24 * 8).status_code, 400)
        self.assertEqual(self.create(question="").status_code, 400)
        self.assertEqual(APIClient().post("/api/v1/posts/poll/", {}, format="json").status_code, 401)

    def test_closed_poll_rejects_votes_and_shows_results(self):
        post = self.create().data
        Poll.objects.filter(discussion_id=post["id"]).update(closes_at=timezone.now() - timedelta(minutes=1))
        url = f"/api/v1/discussions/{post['id']}/vote/"
        self.assertEqual(self.v.post(url, {"option_ids": [post["poll"]["options"][0]["id"]]}, format="json").status_code, 400)
        poll = self.v.get(f"/api/v1/discussions/{post['id']}/").data["poll"]
        self.assertTrue(poll["is_closed"])
        self.assertTrue(poll["results_visible"])

    def test_blocked_people_cannot_see_or_vote(self):
        post = self.create().data
        Block.objects.create(blocker=self.author, blocked=self.voter)
        response = self.v.post(f"/api/v1/discussions/{post['id']}/vote/", {"option_ids": [post["poll"]["options"][0]["id"]]}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_polls_filter_and_feed_queries_stay_flat(self):
        for _ in range(3):
            self.create()
        Discussion.objects.create(author=self.author, title="Plain", body="no poll")
        polls = self.v.get("/api/v1/discussions/?media=polls").data["results"]
        self.assertEqual(len(polls), 3)

        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.v.get("/api/v1/discussions/").status_code, 200)
            return len(ctx)

        few = count()
        for _ in range(8):
            self.create(allows_multiple=False)
        self.assertLessEqual(count(), few + 1, "polls must be loaded in bulk, not per post")


def tiny_mp4():
    # Enough of an MP4 header for the signature check ("ftyp" at offset 4).
    return SimpleUploadedFile("clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048, content_type="video/mp4")


def poster():
    buf = BytesIO()
    Image.new("RGB", (720, 1280), (20, 120, 200)).save(buf, "JPEG")
    return SimpleUploadedFile("poster.jpg", buf.getvalue(), content_type="image/jpeg")


class VideoPostTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user("filmmaker", password="x")
        self.client.force_authenticate(self.author)

    def create(self, **overrides):
        data = {"video": tiny_mp4(), "poster": poster(), "duration_ms": "12500", "caption": "Sunset #reels", "alt_text": "Waves"}
        data.update(overrides)
        data = {k: v for k, v in data.items() if v is not None}
        return self.client.post("/api/v1/posts/video/", data, format="multipart")

    def test_upload_and_stream_with_range(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        media = response.data["attachments"][0]
        self.assertTrue(media["is_video"])
        self.assertFalse(media["is_image"])
        self.assertEqual(media["duration_ms"], 12500)
        self.assertEqual((media["width"], media["height"]), (720, 1280))
        self.assertTrue(media["display_url"].startswith(f"/api/v1/images/{media['id']}/"), "poster is served like a photo")
        self.assertTrue(media["video_url"].startswith(f"/api/v1/videos/{media['id']}/?t="))

        anonymous = APIClient()
        full = anonymous.get(media["video_url"])
        self.assertEqual(full.status_code, 200)
        self.assertEqual(full["Content-Type"], "video/mp4")
        part = anonymous.get(media["video_url"], HTTP_RANGE="bytes=0-15")
        self.assertEqual(part.status_code, 206)
        self.assertEqual(part.content if not part.streaming else b"".join(part.streaming_content), b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4)
        self.assertEqual(anonymous.get(f"/api/v1/videos/{media['id']}/?t=forged").status_code, 403)
        # A photo-variant token can't unlock the video.
        display_token = media["display_url"].split("t=")[1]
        self.assertEqual(anonymous.get(f"/api/v1/videos/{media['id']}/?t={display_token}").status_code, 403)

        videos = self.client.get("/api/v1/discussions/?media=videos").data["results"]
        self.assertEqual([p["id"] for p in videos], [response.data["id"]])
        self.assertEqual(self.client.get("/api/v1/discussions/?media=photos").data["results"], [])

    def test_rejects_bad_uploads(self):
        fake = SimpleUploadedFile("clip.mp4", b"not a video at all" * 10, content_type="video/mp4")
        self.assertEqual(self.create(video=fake).status_code, 400)
        self.assertEqual(self.create(poster=None).status_code, 400)
        self.assertEqual(self.create(duration_ms="0").status_code, 400)
        self.assertEqual(self.create(duration_ms=str(181_000)).status_code, 400)
        self.assertEqual(DiscussionAttachment.objects.count(), 0)
        self.assertEqual(Discussion.objects.count(), 0)
