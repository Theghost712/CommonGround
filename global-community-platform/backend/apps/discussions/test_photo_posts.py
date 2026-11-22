from io import BytesIO, StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from .models import Discussion, DiscussionAttachment

User = get_user_model()


def photo(name="p.jpg", size=(2400, 3000), colour=(200, 40, 60), gps=True):
    buf = BytesIO()
    exif = Image.Exif()
    exif[0x010F] = "TestPhone"
    if gps:
        exif.get_ifd(0x8825)[2] = (3.0, 20.0, 0.0)
    Image.new("RGB", size, colour).save(buf, "JPEG", exif=exif.tobytes())
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


class PhotoPostTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user(username="photographer", password="Strong-pass-123")
        self.client.force_authenticate(self.author)

    def create(self, images, **extra):
        return self.client.post("/api/v1/posts/", {"images": images, **extra}, format="multipart")

    def test_post_with_several_photos_in_one_request(self):
        response = self.create([photo("a.jpg"), photo("b.jpg", size=(1600, 900))], alt_texts=["Red square", "Wide red"], caption="Weekend in Arusha #travel")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["title"], "")
        self.assertEqual(response.data["body"], "Weekend in Arusha #travel")
        first, second = response.data["attachments"]
        self.assertEqual((first["width"], first["height"]), (1080, 1350))
        self.assertEqual(first["alt_text"], "Red square")
        self.assertEqual(second["alt_text"], "Wide red")
        self.assertRegex(first["color"], r"^#[0-9a-f]{6}$")
        self.assertTrue(first["display_url"].startswith(f"/api/v1/images/{first['id']}/?t="))
        self.assertTrue(first["thumb_url"])

    def test_location_data_is_never_stored_even_as_the_original(self):
        self.create([photo()])
        attachment = DiscussionAttachment.objects.get()
        for field in (attachment.file, attachment.display, attachment.thumbnail):
            with field.open("rb") as handle:
                image = Image.open(handle)
                self.assertEqual(image.format, "WEBP")
                self.assertEqual(len(image.getexif()), 0)
        self.assertEqual(attachment.file.name, attachment.display.name)

    def test_one_bad_photo_rejects_the_whole_post_and_leaves_no_files(self):
        storage = DiscussionAttachment._meta.get_field("display").storage
        bad = SimpleUploadedFile("bad.jpg", b"not really a photo", content_type="image/jpeg")
        with mock.patch.object(storage, "delete", wraps=storage.delete) as deleted:
            response = self.create([photo("ok.jpg"), bad])

        self.assertEqual(response.status_code, 400)
        self.assertIn("Photo 2", str(response.data["images"]))
        self.assertFalse(Discussion.objects.exists())
        self.assertFalse(DiscussionAttachment.objects.exists())
        self.assertGreaterEqual(deleted.call_count, 2)  # display + thumbnail of the good photo cleaned up

    def test_limits(self):
        self.assertEqual(self.create([]).status_code, 400)
        eleven = [photo(f"{i}.jpg", size=(40, 40), gps=False) for i in range(11)]
        self.assertEqual(self.create(eleven).status_code, 400)
        self.assertEqual(self.create([photo(size=(40, 40))], caption="x" * 2201).status_code, 400)

    def test_regular_discussions_still_need_a_title(self):
        response = self.client.post("/api/v1/discussions/", {"title": "", "body": "text"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("title", response.data)

    def test_signed_image_links(self):
        data = self.create([photo(size=(800, 800))]).data["attachments"][0]
        anonymous = APIClient()
        ok = anonymous.get(data["display_url"])
        thumb = anonymous.get(data["thumb_url"])
        tampered = anonymous.get(data["display_url"][:-2] + "xx")

        self.assertEqual((ok.status_code, ok["Content-Type"]), (200, "image/webp"))
        self.assertIn("immutable", ok["Cache-Control"])
        self.assertEqual(thumb.status_code, 200)
        self.assertEqual(tampered.status_code, 403)
        with mock.patch("apps.discussions.images.IMAGE_LINK_SECONDS", -1):
            self.assertEqual(anonymous.get(data["display_url"]).status_code, 403)

    def test_photos_filter_for_explore(self):
        self.create([photo(size=(50, 50))], caption="with photo")
        Discussion.objects.create(author=self.author, title="Text only", body="t")
        captions = [d["body"] for d in self.client.get("/api/v1/discussions/", {"media": "photos"}).data["results"]]
        self.assertEqual(captions, ["with photo"])

    def test_old_attachment_upload_endpoint_also_cleans_photos(self):
        post = Discussion.objects.create(author=self.author, title="T", body="b")
        response = self.client.post(f"/api/v1/discussions/{post.id}/attachments/", {"file": photo(size=(300, 300))}, format="multipart")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["display_url"])


class LegacyPhotoTests(APITestCase):
    def setUp(self):
        self.author = User.objects.create_user(username="old_timer", password="Strong-pass-123")
        self.post = Discussion.objects.create(author=self.author, title="Old", body="b")
        raw = photo(size=(1200, 900))
        self.attachment = DiscussionAttachment.objects.create(
            discussion=self.post, uploaded_by=self.author, file=raw, original_name="poster.jpg", content_type="image/jpeg", size=raw.size,
        )

    def test_backfill_creates_copies_and_downloads_serve_the_clean_copy(self):
        call_command("optimize_post_images", stdout=StringIO())
        self.attachment.refresh_from_db()

        self.assertTrue(self.attachment.display and self.attachment.thumbnail)
        self.assertEqual((self.attachment.width, self.attachment.height), (1080, 810))
        with self.attachment.file.open("rb") as handle:
            self.assertEqual(Image.open(handle).format, "JPEG")  # original untouched on disk

        self.client.force_authenticate(self.author)
        download = self.client.get(f"/api/v1/attachments/{self.attachment.id}/download/")
        body = b"".join(download.streaming_content)
        self.assertEqual(download["Content-Type"], "image/webp")
        self.assertEqual(len(Image.open(BytesIO(body)).getexif()), 0)

    def test_backfill_is_idempotent_and_has_dry_run(self):
        out = StringIO()
        call_command("optimize_post_images", "--dry-run", stdout=out)
        self.assertIn("would optimise", out.getvalue())
        call_command("optimize_post_images", stdout=StringIO())
        again = StringIO()
        call_command("optimize_post_images", stdout=again)
        self.assertIn("Optimised 0", again.getvalue())

    def test_unreadable_legacy_file_is_skipped_not_fatal(self):
        DiscussionAttachment.objects.create(discussion=self.post, uploaded_by=self.author, file=ContentFile(b"junk", name="broken.jpg"), original_name="broken.jpg", content_type="image/jpeg")
        out = StringIO()
        call_command("optimize_post_images", stdout=out, stderr=StringIO())
        self.assertIn("Optimised 1 photo(s); 1 skipped.", out.getvalue())
