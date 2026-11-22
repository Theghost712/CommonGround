from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.communities.models import Community, CommunityMembership
from .models import Discussion, DiscussionAttachment, DiscussionBookmark, DiscussionReaction

User = get_user_model()


class DiscussionForumAPITests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user(username="author", password="StrongPass123!")
        self.reader = User.objects.create_user(username="reader", password="StrongPass123!")
        self.discussion = Discussion.objects.create(
            author=self.author,
            title="A useful conversation",
            body="Let's discuss this topic.",
            category="Technology",
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_public_discussions_are_listed(self):
        response = self.client.get("/api/v1/discussions/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]["title"], self.discussion.title)

    def test_discussion_html_is_sanitized(self):
        self.authenticate(self.author)
        response = self.client.patch(
            f"/api/v1/discussions/{self.discussion.id}/",
            {"content_html": "<p>Hello</p><script>alert(1)</script>"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("<p>Hello</p>", response.data["content_html"])
        self.assertNotIn("script", response.data["content_html"])

    def test_reaction_toggles_and_changes_type(self):
        self.authenticate(self.reader)
        url = f"/api/v1/discussions/{self.discussion.id}/react/"
        first = self.client.post(url, {"reaction_type": "insightful"}, format="json")
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertTrue(first.data["reacted"])
        self.assertEqual(first.data["reaction_type"], "insightful")
        second = self.client.post(url, {"reaction_type": "insightful"}, format="json")
        self.assertFalse(second.data["reacted"])
        self.assertEqual(DiscussionReaction.objects.count(), 0)

    def test_bookmark_can_be_saved_and_removed(self):
        self.authenticate(self.reader)
        url = f"/api/v1/discussions/{self.discussion.id}/bookmark/"
        saved = self.client.post(url)
        self.assertTrue(saved.data["bookmarked"])
        self.assertEqual(DiscussionBookmark.objects.count(), 1)
        removed = self.client.post(url)
        self.assertFalse(removed.data["bookmarked"])
        self.assertEqual(DiscussionBookmark.objects.count(), 0)

    def test_comments_support_nested_replies(self):
        self.authenticate(self.reader)
        url = f"/api/v1/discussions/{self.discussion.id}/comments/"
        root = self.client.post(url, {"body": "First comment"}, format="json")
        self.assertEqual(root.status_code, status.HTTP_201_CREATED)
        reply = self.client.post(url, {"body": "A reply", "parent": root.data["id"]}, format="json")
        self.assertEqual(reply.status_code, status.HTTP_201_CREATED)
        listing = self.client.get(url)
        self.assertEqual(listing.data[0]["replies"][0]["body"], "A reply")

    def test_search_and_categories_endpoints(self):
        search = self.client.get("/api/v1/discussions/", {"search": "useful"})
        self.assertEqual(search.data["count"], 1)
        categories = self.client.get("/api/v1/discussions/categories/")
        names = [item["name"] for item in categories.data]
        self.assertIn("Technology", names)

    def test_trending_endpoint_returns_discussions(self):
        response = self.client.get("/api/v1/discussions/trending/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"][0]["id"], self.discussion.id)

    def test_attachment_upload_accepts_allowed_image(self):
        from io import BytesIO

        from PIL import Image

        self.authenticate(self.author)
        buffer = BytesIO()
        Image.new("RGB", (64, 48), (10, 120, 200)).save(buffer, "PNG")
        upload = SimpleUploadedFile("cover.png", buffer.getvalue(), content_type="image/png")
        response = self.client.post(
            f"/api/v1/discussions/{self.discussion.id}/attachments/",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["original_name"], "cover.png")

    def test_fake_images_are_rejected(self):
        self.authenticate(self.author)
        upload = SimpleUploadedFile("cover.png", b"fake-image-bytes", content_type="image/png")
        response = self.client.post(f"/api/v1/discussions/{self.discussion.id}/attachments/", {"file": upload}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_the_author_can_add_attachments(self):
        self.authenticate(self.reader)
        upload = SimpleUploadedFile("intruder.png", b"fake-image-bytes", content_type="image/png")
        response = self.client.post(
            f"/api/v1/discussions/{self.discussion.id}/attachments/",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(DiscussionAttachment.objects.filter(original_name="intruder.png").exists())


class CommunityDiscussionAccessTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="community_owner", password="StrongPass123!")
        self.member = User.objects.create_user(username="community_member", password="StrongPass123!")
        self.outsider = User.objects.create_user(username="community_outsider", password="StrongPass123!")
        self.community = Community.objects.create(
            name="Access controlled",
            description="Access policy test community",
            created_by=self.owner,
            visibility=Community.PUBLIC,
            approval_status=Community.APPROVED,
        )
        for user, role in [(self.owner, CommunityMembership.OWNER), (self.member, CommunityMembership.MEMBER)]:
            CommunityMembership.objects.create(
                community=self.community, user=user, role=role,
                status=CommunityMembership.ACTIVE,
            )
        self.discussion = Discussion.objects.create(
            community=self.community, author=self.owner,
            title="Community discussion", body="Community access policy.",
        )
        self.comment = self.discussion.comments.create(author=self.owner, body="Community comment")
        self.attachment = DiscussionAttachment.objects.create(
            discussion=self.discussion,
            uploaded_by=self.owner,
            file=SimpleUploadedFile("access.txt", b"private attachment", content_type="text/plain"),
            original_name="access.txt", content_type="text/plain", size=19,
        )

    def test_pending_rejected_and_suspended_content_is_hidden_from_creator(self):
        self.client.force_authenticate(self.owner)
        for approval_status in [Community.PENDING, Community.REJECTED, Community.SUSPENDED]:
            with self.subTest(approval_status=approval_status):
                self.community.approval_status = approval_status
                self.community.save(update_fields=["approval_status"])
                self.assertEqual(self.client.get(f"/api/v1/discussions/{self.discussion.id}/").status_code, status.HTTP_404_NOT_FOUND)
                self.assertEqual(self.client.get(f"/api/v1/comments/{self.comment.id}/").status_code, status.HTTP_404_NOT_FOUND)
                self.assertEqual(self.client.get(f"/api/v1/attachments/{self.attachment.id}/download/").status_code, status.HTTP_404_NOT_FOUND)

    def test_approved_public_discussion_comment_and_attachment_are_public(self):
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(f"/api/v1/discussions/{self.discussion.id}/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(f"/api/v1/comments/{self.comment.id}/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(f"/api/v1/attachments/{self.attachment.id}/download/").status_code, status.HTTP_200_OK)

    def test_private_and_restricted_content_requires_active_membership(self):
        for visibility in [Community.PRIVATE, Community.RESTRICTED]:
            with self.subTest(visibility=visibility):
                self.community.visibility = visibility
                self.community.save(update_fields=["visibility"])
                self.client.force_authenticate(self.outsider)
                self.assertEqual(self.client.get(f"/api/v1/discussions/{self.discussion.id}/").status_code, status.HTTP_404_NOT_FOUND)
                self.assertEqual(self.client.get(f"/api/v1/comments/{self.comment.id}/").status_code, status.HTTP_404_NOT_FOUND)
                self.assertEqual(self.client.get(f"/api/v1/attachments/{self.attachment.id}/download/").status_code, status.HTTP_403_FORBIDDEN)
                self.client.force_authenticate(self.member)
                self.assertEqual(self.client.get(f"/api/v1/discussions/{self.discussion.id}/").status_code, status.HTTP_200_OK)
                self.assertEqual(self.client.get(f"/api/v1/comments/{self.comment.id}/").status_code, status.HTTP_200_OK)
                self.assertEqual(self.client.get(f"/api/v1/attachments/{self.attachment.id}/download/").status_code, status.HTTP_200_OK)

    def test_community_creator_cannot_create_discussion_before_approval(self):
        self.community.approval_status = Community.PENDING
        self.community.save(update_fields=["approval_status"])
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            "/api/v1/discussions/",
            {"community": self.community.id, "title": "Bypass", "body": "Not approved yet"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class DiscussionAndCommentEditingTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user(username="edit_author", password="StrongPass123!")
        self.other = User.objects.create_user(username="edit_other", password="StrongPass123!")
        self.discussion = Discussion.objects.create(author=self.author, title="Original", body="Original body")
        self.other_discussion = Discussion.objects.create(author=self.other, title="Elsewhere", body="Another thread")
        self.comment = self.discussion.comments.create(author=self.author, body="First thought")
        self.parent = self.discussion.comments.create(author=self.other, body="Parent")

    def test_author_can_edit_and_delete_own_discussion(self):
        self.client.force_authenticate(self.author)
        edited = self.client.patch(
            f"/api/v1/discussions/{self.discussion.id}/",
            {"title": "Updated", "body": "Updated body", "content_html": "<p>Updated <script>x</script>body</p>", "category": "Health"},
            format="json",
        )
        self.assertEqual(edited.status_code, status.HTTP_200_OK)
        self.assertEqual(edited.data["title"], "Updated")
        self.assertNotIn("<script>", edited.data["content_html"])

        deleted = self.client.delete(f"/api/v1/discussions/{self.discussion.id}/")
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Discussion.objects.filter(pk=self.discussion.id).exists())

    def test_others_cannot_edit_or_delete_a_discussion(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.patch(f"/api/v1/discussions/{self.discussion.id}/", {"title": "Hijack"}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(f"/api/v1/discussions/{self.discussion.id}/").status_code, status.HTTP_403_FORBIDDEN)

    def test_author_can_edit_and_delete_own_comment(self):
        self.client.force_authenticate(self.author)
        edited = self.client.patch(f"/api/v1/comments/{self.comment.id}/", {"body": "Second thought"}, format="json")
        self.assertEqual(edited.status_code, status.HTTP_200_OK)
        self.assertEqual(edited.data["body"], "Second thought")
        self.assertEqual(self.client.delete(f"/api/v1/comments/{self.comment.id}/").status_code, status.HTTP_204_NO_CONTENT)

    def test_others_cannot_edit_or_delete_a_comment(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.patch(f"/api/v1/comments/{self.comment.id}/", {"body": "Nope"}, format="json").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(f"/api/v1/comments/{self.comment.id}/").status_code, status.HTTP_403_FORBIDDEN)

    def test_editing_a_comment_cannot_move_or_reparent_it(self):
        self.client.force_authenticate(self.author)
        response = self.client.patch(
            f"/api/v1/comments/{self.comment.id}/",
            {"body": "Still here", "discussion": self.other_discussion.id, "parent": self.parent.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.comment.refresh_from_db()
        self.assertEqual((self.comment.discussion_id, self.comment.parent_id, self.comment.body), (self.discussion.id, None, "Still here"))
