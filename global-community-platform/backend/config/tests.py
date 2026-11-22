from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.test import TestCase

from apps.communities.models import Community


class AdminBrandingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = get_user_model().objects.create_superuser(
            username="dashboard_admin",
            email="admin@example.test",
            password="StrongPass123!",
        )
        cls.community = Community.objects.create(
            name="Dashboard review",
            description="Admin dashboard fixture",
            created_by=cls.admin_user,
            approval_status=Community.PENDING,
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_admin_dashboard_renders_brand_stats_and_app_links(self):
        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CommonGround")
        self.assertContains(response, "Platform overview")
        self.assertContains(response, "Platform statistics")
        self.assertContains(response, "Awaiting review")
        self.assertContains(response, "Apps and records")
        self.assertContains(response, "Recent activity")
        self.assertContains(response, "commonground-admin.css")

    def test_admin_changelist_keeps_community_approval_actions(self):
        response = self.client.get("/admin/communities/community/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approve selected communities")
        self.assertContains(response, "Reject selected communities")
        self.assertContains(response, "Suspend selected communities")
        self.assertContains(response, "Restore suspended communities")
        self.assertContains(response, "commonground-admin.css")

    def test_admin_stylesheet_is_discoverable_by_staticfiles(self):
        path = finders.find("admin/css/commonground-admin.css")

        self.assertIsNotNone(path)
        self.assertTrue(path.endswith("commonground-admin.css"))


import os
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from config.settings import load_env_file

BACKEND_DIR = Path(__file__).resolve().parent.parent
PRODUCTION_ENV = {
    "DJANGO_ENV": "production",
    "DJANGO_DEBUG": "False",
    "DJANGO_SECRET_KEY": "a-real-production-secret",
    "DJANGO_ALLOWED_HOSTS": "example.org",
    "CORS_ALLOWED_ORIGINS": "https://example.org",
    "CSRF_TRUSTED_ORIGINS": "https://example.org",
    "DATABASE_URL": "postgresql://u:p@db.example.org:5432/app",
    "REDIS_URL": "redis://cache.example.org:6379/0",
    "FRONTEND_URL": "https://example.org",
    "EMAIL_HOST": "smtp.example.org",
}


def import_settings(**overrides):
    """Import settings in a fresh interpreter with a controlled environment."""
    env = {key: value for key, value in os.environ.items() if key not in PRODUCTION_ENV}
    env.update(overrides)
    return subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=60,
    )


class EnvFileLoaderTests(SimpleTestCase):
    def setUp(self):
        self.keys = ["CG_TEST_PLAIN", "CG_TEST_QUOTED", "CG_TEST_EXPORT", "CG_TEST_EXISTING", "CG_TEST_EQUALS"]
        self.addCleanup(lambda: [os.environ.pop(key, None) for key in self.keys])

    def test_parses_values_and_never_overrides_real_environment(self):
        os.environ["CG_TEST_EXISTING"] = "from-shell"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "# comment\n\nCG_TEST_PLAIN=plain\nCG_TEST_QUOTED=\"two words\"\n"
                "export CG_TEST_EXPORT='exported'\nCG_TEST_EXISTING=from-file\n"
                "CG_TEST_EQUALS=a=b=c\nnot a setting\n",
                encoding="utf-8",
            )
            load_env_file(path)
        self.assertEqual(os.environ["CG_TEST_PLAIN"], "plain")
        self.assertEqual(os.environ["CG_TEST_QUOTED"], "two words")
        self.assertEqual(os.environ["CG_TEST_EXPORT"], "exported")
        self.assertEqual(os.environ["CG_TEST_EXISTING"], "from-shell")
        self.assertEqual(os.environ["CG_TEST_EQUALS"], "a=b=c")

    def test_missing_file_is_ignored(self):
        load_env_file(Path("/nonexistent/commonground/.env"))


class ProductionSettingsGuardTests(SimpleTestCase):
    def test_complete_production_configuration_loads(self):
        result = import_settings(**PRODUCTION_ENV)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_required_values_are_named(self):
        result = import_settings(**{**PRODUCTION_ENV, "DJANGO_SECRET_KEY": "", "REDIS_URL": " "})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY, REDIS_URL", result.stderr)

    def test_debug_is_rejected_in_production(self):
        result = import_settings(**{**PRODUCTION_ENV, "DJANGO_DEBUG": "True"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_DEBUG=False", result.stderr)

    def test_email_links_must_use_https_frontend(self):
        result = import_settings(**{**PRODUCTION_ENV, "FRONTEND_URL": "http://example.org"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FRONTEND_URL", result.stderr)

    def test_smtp_needs_a_host(self):
        result = import_settings(**{**PRODUCTION_ENV, "EMAIL_HOST": ""})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("EMAIL_HOST", result.stderr)


class TestMediaIsolationTests(SimpleTestCase):
    def test_tests_never_write_to_the_real_media_folder(self):
        self.assertNotEqual(Path(settings.MEDIA_ROOT).resolve(), (BACKEND_DIR / "media").resolve())
        self.assertIn("commonground-test-media-", str(settings.MEDIA_ROOT))


class HealthCheckTests(SimpleTestCase):
    databases = {"default"}

    def test_reports_ok_when_database_and_cache_answer(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checks"], {"database": "ok", "cache": "ok"})
        self.assertIn("no-cache", response["Cache-Control"])

    def test_reports_503_when_the_database_is_down(self):
        from unittest import mock

        with mock.patch("apps.common.health.connection.cursor", side_effect=RuntimeError("down")):
            response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"]["database"], "error")


class HealthCheckBehindProxyTests(SimpleTestCase):
    databases = {"default"}

    def test_probe_by_internal_ip_is_not_rejected_by_allowed_hosts(self):
        response = self.client.get("/api/v1/health/", HTTP_HOST="10.204.1.7:10000")
        self.assertEqual(response.status_code, 200)

    def test_other_paths_still_validate_the_host(self):
        self.assertEqual(self.client.get("/api/v1/discussions/", HTTP_HOST="evil.example").status_code, 400)
