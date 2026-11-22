import re
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import UserProfile
from .security import make_email_token

User = get_user_model()
PASSWORD = "Original-pass-123"
NEW_PASSWORD = "Brand-new-pass-456"


def link_in(message, path):
    match = re.search(rf"https?://\S+{re.escape(path)}\?\S+", message.body)
    assert match, f"no {path} link in: {message.body}"
    return match.group(0)


def query_param(link, name):
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(link).query)[name][0]


@override_settings(FRONTEND_URL="https://app.example.test")
class AccountSecurityBase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("amina", "amina@example.com", PASSWORD, first_name="Amina")
        UserProfile.objects.get_or_create(user=self.user)

    def login(self, client=None, password=PASSWORD, earlier=True):
        """Sign in. By default the session is backdated a few seconds.

        JWT "iat" has whole-second precision and revocation cuts at the start of
        the revoking second, so sessions that should die must be issued in an
        earlier second than the revocation (as they always are in real life).
        """
        client = client or APIClient()
        if earlier:
            from rest_framework_simplejwt.utils import aware_utcnow

            past = aware_utcnow() - timedelta(seconds=5)
            with mock.patch("rest_framework_simplejwt.tokens.aware_utcnow", return_value=past):
                return self.login(client, password, earlier=False)
        response = client.post("/api/v1/auth/token/", {"username": "amina", "password": password}, format="json")
        if response.status_code == 200:
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return client, response


class RegistrationEmailTests(AccountSecurityBase):
    def register(self, **overrides):
        data = {"username": "newbie", "email": "newbie@example.com", "password": PASSWORD, "password_confirm": PASSWORD}
        data.update(overrides)
        return self.client.post("/api/v1/auth/register/", data, format="json")

    def test_registration_sends_verification_and_link_confirms_email(self):
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["newbie@example.com"])
        link = link_in(mail.outbox[0], "/verify-email")
        self.assertTrue(link.startswith("https://app.example.test/verify-email?token="))

        client, _ = APIClient(), None
        login = client.post("/api/v1/auth/token/", {"username": "newbie", "password": PASSWORD}, format="json")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        self.assertFalse(client.get("/api/v1/auth/me/").data["email_verified"])

        response = APIClient().post("/api/v1/auth/email/verify/", {"token": query_param(link, "token")}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(client.get("/api/v1/auth/me/").data["email_verified"])
        # Using it again is harmless.
        again = APIClient().post("/api/v1/auth/email/verify/", {"token": query_param(link, "token")}, format="json")
        self.assertEqual(again.status_code, 200)

    def test_email_is_required_and_unique_case_insensitively(self):
        self.assertEqual(self.register(email="").status_code, 400)
        response = self.register(email="AMINA@example.com")
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_smtp_failure_does_not_break_registration(self):
        with mock.patch("apps.accounts.security.send_mail", side_effect=OSError("smtp down")), \
                self.assertLogs("apps.accounts.security", "ERROR"):
            self.assertEqual(self.register().status_code, 201)

    def test_me_endpoint_cannot_change_email_directly(self):
        client, _ = self.login()
        client.patch("/api/v1/auth/me/", {"email": "evil@example.com"}, format="json")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "amina@example.com")


class EmailLinkTests(AccountSecurityBase):
    def test_bad_tampered_and_expired_tokens_are_rejected(self):
        token = make_email_token(self.user)
        for bad in ["", "garbage", token[:-2] + "xx"]:
            self.assertEqual(self.client.post("/api/v1/auth/email/verify/", {"token": bad}, format="json").status_code, 400)
        with override_settings(EMAIL_LINK_MAX_AGE_SECONDS=-1):
            self.assertEqual(self.client.post("/api/v1/auth/email/verify/", {"token": token}, format="json").status_code, 400)

    def test_link_dies_when_the_email_changes(self):
        token = make_email_token(self.user)
        self.user.email = "other@example.com"
        self.user.save()
        self.assertEqual(self.client.post("/api/v1/auth/email/verify/", {"token": token}, format="json").status_code, 400)

    def test_resend_verification(self):
        client, _ = self.login()
        response = client.post("/api/v1/auth/email/resend/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("a••••@example.com", response.data["detail"])
        self.assertEqual(len(mail.outbox), 1)
        UserProfile.objects.filter(user=self.user).update(email_verified_at="2026-01-01T00:00Z")
        self.assertIn("already", client.post("/api/v1/auth/email/resend/").data["detail"])
        self.assertEqual(len(mail.outbox), 1)

    def test_change_email_needs_password_and_confirmation_from_new_inbox(self):
        client, _ = self.login()
        wrong = client.post("/api/v1/auth/email/change/", {"new_email": "new@example.com", "password": "nope"}, format="json")
        self.assertEqual(wrong.status_code, 400)
        User.objects.create_user("taken", "taken@example.com", PASSWORD)
        taken = client.post("/api/v1/auth/email/change/", {"new_email": "Taken@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(taken.status_code, 400)
        invalid = client.post("/api/v1/auth/email/change/", {"new_email": "not-an-email", "password": PASSWORD}, format="json")
        self.assertEqual(invalid.status_code, 400)

        response = client.post("/api/v1/auth/email/change/", {"new_email": "new@example.com", "password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "amina@example.com", "email must not change before confirmation")
        to_new, to_old = mail.outbox
        self.assertEqual(to_new.to, ["new@example.com"])
        self.assertEqual(to_old.to, ["amina@example.com"])
        self.assertNotIn("new@example.com", to_old.body, "old inbox only sees a masked address")

        token = query_param(link_in(to_new, "/verify-email"), "token")
        confirmed = APIClient().post("/api/v1/auth/email/verify/", {"token": token}, format="json")
        self.assertEqual(confirmed.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "new@example.com")
        self.assertTrue(client.get("/api/v1/auth/me/").data["email_verified"])
        # Single use: the link names the old address, which is gone now.
        self.assertEqual(APIClient().post("/api/v1/auth/email/verify/", {"token": token}, format="json").status_code, 400)


class PasswordResetTests(AccountSecurityBase):
    def request_reset(self, login):
        return self.client.post("/api/v1/auth/password/reset/", {"login": login}, format="json")

    def test_same_answer_for_known_and_unknown_accounts(self):
        known = self.request_reset("amina@example.com")
        unknown = self.request_reset("nobody@example.com")
        self.assertEqual(known.status_code, 200)
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.request_reset("AMINA").status_code, 200)  # by username, any case
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(self.request_reset("").status_code, 400)

    def test_no_email_for_inactive_users(self):
        self.user.is_active = False
        self.user.save()
        self.request_reset("amina")
        self.assertEqual(len(mail.outbox), 0)

    def test_full_reset_flow_signs_out_everywhere_and_link_is_single_use(self):
        client, _ = self.login()
        cookie = client.cookies[settings.REFRESH_COOKIE_NAME].value
        self.request_reset("amina@example.com")
        link = link_in(mail.outbox[0], "/reset-password")
        uid, token = query_param(link, "uid"), query_param(link, "token")

        weak = self.client.post("/api/v1/auth/password/reset/confirm/",
                                {"uid": uid, "token": token, "new_password": "123", "new_password_confirm": "123"}, format="json")
        self.assertEqual(weak.status_code, 400)
        self.assertIn("new_password", weak.data)

        done = self.client.post("/api/v1/auth/password/reset/confirm/",
                                {"uid": uid, "token": token, "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD},
                                format="json")
        self.assertEqual(done.status_code, 200)
        self.assertEqual(mail.outbox[-1].subject, "CommonGround: your password was changed")
        # The old session's access and refresh tokens are dead.
        self.assertEqual(client.get("/api/v1/auth/me/").status_code, 401)
        stale = APIClient()
        stale.cookies[settings.REFRESH_COOKIE_NAME] = cookie
        self.assertEqual(stale.post("/api/v1/auth/token/refresh/").status_code, 401)
        # Link can't be reused, old password fails, new one works, and the email counts as verified.
        again = self.client.post("/api/v1/auth/password/reset/confirm/",
                                 {"uid": uid, "token": token, "new_password": "Another-pass-789", "new_password_confirm": "Another-pass-789"},
                                 format="json")
        self.assertEqual(again.status_code, 400)
        self.assertEqual(self.login(password=PASSWORD)[1].status_code, 401)
        fresh, response = self.login(password=NEW_PASSWORD, earlier=False)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(fresh.get("/api/v1/auth/me/").data["email_verified"])

    def test_garbage_uid_and_token(self):
        for uid, token in [("", ""), ("!!", "x"), ("MQ", "bad-token")]:
            response = self.client.post("/api/v1/auth/password/reset/confirm/",
                                        {"uid": uid, "token": token, "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD},
                                        format="json")
            self.assertEqual(response.status_code, 400)


class PasswordChangeAndSessionTests(AccountSecurityBase):
    def test_change_password_keeps_this_device_and_signs_out_others(self):
        phone, _ = self.login()
        laptop, _ = self.login()
        self.assertEqual(laptop.post("/api/v1/auth/password/change/",
                                     {"current_password": "wrong", "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD},
                                     format="json").status_code, 400)
        same = laptop.post("/api/v1/auth/password/change/",
                           {"current_password": PASSWORD, "new_password": PASSWORD, "new_password_confirm": PASSWORD}, format="json")
        self.assertEqual(same.status_code, 400)
        mismatch = laptop.post("/api/v1/auth/password/change/",
                               {"current_password": PASSWORD, "new_password": NEW_PASSWORD, "new_password_confirm": "x"}, format="json")
        self.assertIn("new_password_confirm", mismatch.data)

        response = laptop.post("/api/v1/auth/password/change/",
                               {"current_password": PASSWORD, "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD},
                               format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn(settings.REFRESH_COOKIE_NAME, response.cookies)
        self.assertEqual(phone.get("/api/v1/auth/me/").status_code, 401)
        laptop.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        self.assertEqual(laptop.get("/api/v1/auth/me/").status_code, 200)
        self.assertEqual(laptop.post("/api/v1/auth/token/refresh/").status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_sign_out_everywhere(self):
        phone, _ = self.login()
        laptop, _ = self.login()
        response = laptop.post("/api/v1/auth/sessions/revoke/", {"keep_current": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.cookies[settings.REFRESH_COOKIE_NAME].value, "")
        for client in (phone, laptop):
            self.assertEqual(client.get("/api/v1/auth/me/").status_code, 401)
        again, response = self.login(earlier=False)
        self.assertEqual(response.status_code, 200, "signing in again works")
        self.assertEqual(again.get("/api/v1/auth/me/").status_code, 200)

    def test_sign_out_other_devices_keeps_this_one(self):
        phone, _ = self.login()
        laptop, _ = self.login()
        response = laptop.post("/api/v1/auth/sessions/revoke/", {"keep_current": True}, format="json")
        self.assertEqual(phone.get("/api/v1/auth/me/").status_code, 401)
        self.assertEqual(phone.post("/api/v1/auth/token/refresh/").status_code, 401)
        laptop.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        self.assertEqual(laptop.get("/api/v1/auth/me/").status_code, 200)

    def test_revocation_survives_a_cold_cache(self):
        from django.core.cache import cache

        phone, _ = self.login()
        self.client.force_authenticate(self.user)
        self.client.post("/api/v1/auth/sessions/revoke/", {}, format="json")
        cache.clear()
        self.assertEqual(phone.get("/api/v1/auth/me/").status_code, 401)

    def test_endpoints_require_sign_in(self):
        for path in ["/api/v1/auth/password/change/", "/api/v1/auth/sessions/revoke/",
                     "/api/v1/auth/email/resend/", "/api/v1/auth/email/change/"]:
            self.assertEqual(APIClient().post(path, {}, format="json").status_code, 401, path)
