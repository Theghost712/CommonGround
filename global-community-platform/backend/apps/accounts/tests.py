import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()
# Tests pin their own origins so they don't depend on this machine's .env.
FRONTEND_ORIGIN = "http://frontend.example.test:5174"
UNTRUSTED_ORIGIN = "http://frontend.example.test:5173"


@override_settings(CSRF_TRUSTED_ORIGINS=[FRONTEND_ORIGIN], CORS_ALLOWED_ORIGINS=[FRONTEND_ORIGIN])
class AuthenticationSecurityTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="security-user", password="Test-pass-12345")

    def csrf_headers(self):
        response = self.client.get("/api/v1/auth/csrf/")
        return {"HTTP_X_CSRFTOKEN": response.json()["csrfToken"]}

    def csrf_token(self, client):
        response = client.get("/api/v1/auth/csrf/")
        return response.json()["csrfToken"]

    def test_frontend_origin_is_configured_for_csrf_and_cors(self):
        self.assertIn(FRONTEND_ORIGIN, settings.CSRF_TRUSTED_ORIGINS)
        self.assertIn(FRONTEND_ORIGIN, settings.CORS_ALLOWED_ORIGINS)
        self.assertTrue(settings.CORS_ALLOW_CREDENTIALS)

    def test_login_accepts_trusted_frontend_origin(self):
        client = APIClient(enforce_csrf_checks=True)
        csrf_token = self.csrf_token(client)
        response = client.post(
            "/api/v1/auth/token/",
            {"username": "security-user", "password": "Test-pass-12345"},
            format="json",
            HTTP_ORIGIN=FRONTEND_ORIGIN,
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        cookie = response.cookies[settings.REFRESH_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["path"], settings.REFRESH_COOKIE_PATH)

    def test_login_rejects_untrusted_frontend_origin(self):
        client = APIClient(enforce_csrf_checks=True)
        csrf_token = self.csrf_token(client)
        response = client.post(
            "/api/v1/auth/token/",
            {"username": "security-user", "password": "Test-pass-12345"},
            format="json",
            HTTP_ORIGIN=UNTRUSTED_ORIGIN,
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, 403)

    def test_login_sets_http_only_refresh_cookie_and_returns_access_only(self):
        response = self.client.post("/api/v1/auth/token/", {"username": "security-user", "password": "Test-pass-12345"}, format="json", **self.csrf_headers())
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        cookie = response.cookies[settings.REFRESH_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["path"], settings.REFRESH_COOKIE_PATH)

    def test_refresh_uses_cookie_and_rotates_token(self):
        self.client.post("/api/v1/auth/token/", {"username": "security-user", "password": "Test-pass-12345"}, format="json", **self.csrf_headers())
        old_refresh = self.client.cookies[settings.REFRESH_COOKIE_NAME].value
        response = self.client.post("/api/v1/auth/token/refresh/", {}, format="json", **self.csrf_headers())
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertNotEqual(self.client.cookies[settings.REFRESH_COOKIE_NAME].value, old_refresh)
        self.assertNotIn("refresh", response.data)

    def test_rotated_refresh_token_cannot_be_reused(self):
        self.client.post("/api/v1/auth/token/", {"username": "security-user", "password": "Test-pass-12345"}, format="json", **self.csrf_headers())
        previous_refresh = self.client.cookies[settings.REFRESH_COOKIE_NAME].value
        self.client.post("/api/v1/auth/token/refresh/", {}, format="json", **self.csrf_headers())

        self.client.cookies[settings.REFRESH_COOKIE_NAME] = previous_refresh
        replay = self.client.post("/api/v1/auth/token/refresh/", {}, format="json", **self.csrf_headers())
        self.assertEqual(replay.status_code, 401)

    def test_logout_revokes_refresh_and_clears_cookie(self):
        self.client.post("/api/v1/auth/token/", {"username": "security-user", "password": "Test-pass-12345"}, format="json", **self.csrf_headers())
        refresh_token = self.client.cookies[settings.REFRESH_COOKIE_NAME].value
        response = self.client.post("/api/v1/auth/logout/", {}, format="json", **self.csrf_headers())
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.cookies[settings.REFRESH_COOKIE_NAME].value, "")

        self.client.cookies[settings.REFRESH_COOKIE_NAME] = refresh_token
        replay = self.client.post("/api/v1/auth/token/refresh/", {}, format="json", **self.csrf_headers())
        self.assertEqual(replay.status_code, 401)

    def test_expired_refresh_token_is_rejected(self):
        token = RefreshToken.for_user(self.user)
        token["exp"] = int(time.time()) - 1
        self.client.cookies[settings.REFRESH_COOKIE_NAME] = str(token)
        response = self.client.post("/api/v1/auth/token/refresh/", {}, format="json", **self.csrf_headers())
        self.assertEqual(response.status_code, 401)

    def test_cookie_auth_endpoints_reject_missing_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        response = client.post("/api/v1/auth/token/", {"username": "security-user", "password": "Test-pass-12345"}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_protected_endpoints_reject_anonymous_users(self):
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/ws-ticket/", {}, format="json").status_code, 401)

    def test_authenticated_user_can_obtain_short_lived_websocket_ticket(self):
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/v1/auth/ws-ticket/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ticket"])

    def test_inactive_user_cannot_obtain_websocket_ticket(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/v1/auth/ws-ticket/", {}, format="json")
        self.assertEqual(response.status_code, 401)


from unittest import mock

from django.core.cache import cache
from rest_framework.throttling import SimpleRateThrottle


@override_settings(CSRF_TRUSTED_ORIGINS=[FRONTEND_ORIGIN], CORS_ALLOWED_ORIGINS=[FRONTEND_ORIGIN])
class LoginRateLimitTests(APITestCase):
    RATES = {"anon": "1000/hour", "user": "5000/hour", "auth": "3/minute"}

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        patcher = mock.patch.object(SimpleRateThrottle, "THROTTLE_RATES", self.RATES)
        patcher.start()
        self.addCleanup(patcher.stop)
        User.objects.create_user(username="limited", password="Test-pass-12345")

    def attempt(self, password="wrong-password", **headers):
        token = self.client.get("/api/v1/auth/csrf/").json()["csrfToken"]
        return self.client.post(
            "/api/v1/auth/token/", {"username": "limited", "password": password},
            format="json", HTTP_X_CSRFTOKEN=token, **headers,
        )

    def test_repeated_logins_are_throttled_with_retry_after(self):
        statuses = [self.attempt().status_code for _ in range(3)]
        blocked = self.attempt(password="Test-pass-12345")

        self.assertEqual(statuses, [401, 401, 401])
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Retry-After", blocked.headers)

    def test_registration_shares_the_login_limit(self):
        for _ in range(3):
            self.attempt()
        token = self.client.get("/api/v1/auth/csrf/").json()["csrfToken"]
        response = self.client.post("/api/v1/auth/register/", {}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 429)

    @override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "NUM_PROXIES": 0})
    def test_forged_forwarded_for_header_cannot_dodge_the_limit_without_proxy(self):
        statuses = [self.attempt(HTTP_X_FORWARDED_FOR=f"10.0.0.{i}").status_code for i in range(4)]
        self.assertEqual(statuses[-1], 429)

    @override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "NUM_PROXIES": 1})
    def test_behind_one_proxy_each_client_gets_its_own_bucket(self):
        # The proxy appends the real client IP last; a forged earlier entry is ignored.
        for _ in range(3):
            self.attempt(HTTP_X_FORWARDED_FOR="203.0.113.5")
        same_client_forging = self.attempt(HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.5")
        other_client = self.attempt(HTTP_X_FORWARDED_FOR="198.51.100.7")

        self.assertEqual(same_client_forging.status_code, 429)
        self.assertEqual(other_client.status_code, 401)


class ThrottleSettingsTests(APITestCase):
    def test_rates_and_proxy_count_are_configured(self):
        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        self.assertEqual(set(rates), {"anon", "user", "auth", "contacts", "uploads", "reports", "account_email", "calls", "payments"})
        self.assertIsInstance(settings.REST_FRAMEWORK["NUM_PROXIES"], int)
