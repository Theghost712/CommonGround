import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.accounts.models import UserProfile
from apps.communities.models import Community
from apps.discussions.models import Discussion

User = get_user_model()
SHELL = """<!doctype html><html><head><meta name="description" content="A global space." /><title>CommonGround — Ideas</title></head><body><div id="root"></div></body></html>"""


@override_settings(FRONTEND_URL="https://cg.example")
class SeoTests(TestCase):
    def setUp(self):
        cache.clear()
        self.dist = Path(tempfile.mkdtemp())
        (self.dist / "index.html").write_text(SHELL, encoding="utf-8")
        self.author = User.objects.create_user("amina", first_name="Amina")
        UserProfile.objects.create(user=self.author)
        self.public = Community.objects.create(name="Dar Founders", description="Startups in <Dar>", created_by=self.author)
        self.private = Community.objects.create(name="Hidden", description="x", visibility=Community.PRIVATE, created_by=self.author)
        self.post = Discussion.objects.create(author=self.author, community=self.public, title='Funding "tips" </script>', body="How do you raise a seed round in Tanzania?")
        self.secret = Discussion.objects.create(author=self.author, community=self.private, title="Secret plans", body="x")
        self.personal = Discussion.objects.create(author=self.author, title="My weekend", body="Beach")

    def get(self, path):
        with override_settings(FRONTEND_DIST=self.dist):
            return self.client.get(path).content.decode()

    def test_public_discussion_has_title_preview_text_and_structured_data(self):
        html = self.get(f"/discussions/{self.post.pk}")
        self.assertIn("<title>Funding &quot;tips&quot; &lt;/script&gt; · CommonGround</title>", html)
        self.assertIn('<meta property="og:title" content="Funding &quot;tips&quot; &lt;/script&gt; · CommonGround" />', html)
        self.assertIn('content="How do you raise a seed round in Tanzania?"', html)
        self.assertIn(f'<link rel="canonical" href="https://cg.example/discussions/{self.post.pk}" />', html)
        self.assertIn('"@type": "DiscussionForumPosting"', html)
        self.assertNotIn("</script> ·", html.split("application/ld+json")[1].split("</script>")[0])  # can't break out of JSON-LD
        self.assertIn('<div id="root"><div class="seo-snapshot">', html)
        self.assertNotIn("noindex", html)
        self.assertEqual(html.count("<title>"), 1)

    def test_personal_posts_get_previews_but_no_indexing_and_private_ones_nothing(self):
        self.assertIn('<meta name="robots" content="noindex" />', self.get(f"/discussions/{self.personal.pk}"))
        for path in [f"/discussions/{self.secret.pk}", f"/communities/{self.private.pk}", "/discussions/99999", "/home"]:
            html = self.get(path)
            self.assertIn("<title>CommonGround — Ideas</title>", html, path)
            self.assertNotIn("Secret plans", html)
            self.assertIn('<div id="root"></div>', html)

    def test_community_page_lists_recent_discussions(self):
        html = self.get(f"/communities/{self.public.pk}")
        self.assertIn("<title>Dar Founders · CommonGround</title>", html)
        self.assertIn("Startups in &lt;Dar&gt;", html)
        self.assertIn(f'href="/discussions/{self.post.pk}"', html)

    def test_sitemap_and_robots(self):
        sitemap = self.client.get("/sitemap.xml")
        self.assertEqual(sitemap["Content-Type"], "application/xml; charset=utf-8")
        body = sitemap.content.decode()
        self.assertIn(f"https://cg.example/discussions/{self.post.pk}</loc>", body)
        self.assertIn(f"https://cg.example/communities/{self.public.pk}</loc>", body)
        for hidden in (self.secret, self.personal):
            self.assertNotIn(f"/discussions/{hidden.pk}<", body)
        self.assertNotIn(f"/communities/{self.private.pk}<", body)
        robots = self.client.get("/robots.txt").content.decode()
        self.assertIn("Disallow: /messages", robots)
        self.assertIn("Sitemap: https://cg.example/sitemap.xml", robots)
