from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from rest_framework.test import APIClient, APITestCase

from .models import TwoFactorAuth
from .two_factor import current_step, decrypt_secret, match_totp, totp

User = get_user_model()
PASSWORD = "Original-pass-123"


class TotpTests(APITestCase):
    def test_rfc6238_vector(self):
        # RFC 6238 appendix B, SHA1, T=59s -> 94287082 (8 digits); the last 6 are ours.
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32 of "12345678901234567890"
        self.assertEqual(totp(secret, 59 // 30), "287082")

    def test_drift_and_replay(self):
        secret = "JBSWY3DPEHPK3PXP"
        now = 1_700_000_000
        step = current_step(now)
        self.assertEqual(match_totp(secret, totp(secret, step - 1), now=now), step - 1)
        self.assertIsNone(match_totp(secret, totp(secret, step - 2), now=now))
        self.assertIsNone(match_totp(secret, totp(secret, step), after_step=step, now=now))
        self.assertIsNone(match_totp(secret, "12345", now=now))


class TwoFactorFlowTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("amina", "amina@example.com", PASSWORD)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def code_now(self, offset=0):
        secret = decrypt_secret(TwoFactorAuth.objects.get(user=self.user).secret_encrypted)
        return totp(secret, current_step() + offset)

    def enable(self):
        setup = self.client.post("/api/v1/auth/2fa/setup/", {"password": PASSWORD}, format="json")
        self.assertEqual(setup.status_code, 200, setup.data)
        confirm = self.client.post("/api/v1/auth/2fa/confirm/", {"code": self.code_now()}, format="json")
        self.assertEqual(confirm.status_code, 200, confirm.data)
        return setup.data, confirm.data["recovery_codes"]

    def password_step(self, client=None):
        client = client or APIClient()
        response = client.post("/api/v1/auth/token/", {"username": "amina", "password": PASSWORD}, format="json")
        return client, response

    def test_setup_requires_password_and_stays_off_until_confirmed(self):
        bad = self.client.post("/api/v1/auth/2fa/setup/", {"password": "nope"}, format="json")
        self.assertEqual(bad.status_code, 400)
        setup = self.client.post("/api/v1/auth/2fa/setup/", {"password": PASSWORD}, format="json")
        self.assertTrue(setup.data["otpauth_uri"].startswith("otpauth://totp/CommonGround%3Aamina?"))
        self.assertIn(f"secret={setup.data['secret']}", setup.data["otpauth_uri"])
        row = TwoFactorAuth.objects.get(user=self.user)
        self.assertNotIn(setup.data["secret"], row.secret_encrypted)
        self.assertFalse(self.client.get("/api/v1/auth/2fa/").data["enabled"])
        # Password sign-in still gives tokens while setup is unconfirmed.
        _, response = self.password_step()
        self.assertIn("access", response.data)
        wrong = self.client.post("/api/v1/auth/2fa/confirm/", {"code": "000000"}, format="json")
        self.assertEqual(wrong.status_code, 400)

    def test_enable_then_two_step_sign_in(self):
        _, codes = self.enable()
        self.assertEqual(len(codes), 10)
        self.assertEqual(len(set(codes)), 10)
        self.assertTrue(any("two-step sign-in is on" in m.subject for m in mail.outbox))
        status = self.client.get("/api/v1/auth/2fa/").data
        self.assertEqual((status["enabled"], status["recovery_codes_left"]), (True, 10))
        self.assertTrue(self.client.get("/api/v1/auth/me/").data["two_factor_enabled"])

        client, first = self.password_step()
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.data["two_factor_required"])
        self.assertNotIn("access", first.data)
        self.assertNotIn("cg_refresh", first.cookies)

        # The code used to confirm can't be replayed; the next one works.
        second = client.post("/api/v1/auth/token/2fa/", {"challenge": first.data["challenge"], "code": self.code_now(1)}, format="json")
        self.assertEqual(second.status_code, 200, second.data)
        self.assertIn("access", second.data)
        self.assertIn("cg_refresh", second.cookies)
        # Same challenge can't be used twice.
        again = client.post("/api/v1/auth/token/2fa/", {"challenge": first.data["challenge"], "code": "123456"}, format="json")
        self.assertEqual(again.status_code, 401)

    def test_wrong_codes_burn_the_challenge(self):
        self.enable()
        client, first = self.password_step()
        challenge = first.data["challenge"]
        for _ in range(5):
            r = client.post("/api/v1/auth/token/2fa/", {"challenge": challenge, "code": "000000"}, format="json")
            self.assertEqual(r.status_code, 400)
        r = client.post("/api/v1/auth/token/2fa/", {"challenge": challenge, "code": self.code_now(1)}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_too_many_wrong_codes_pause_the_account(self):
        self.enable()
        client, first = self.password_step()
        cache.set(f"2fa-user-failures:{self.user.pk}", 9, timeout=900)
        mail.outbox.clear()
        r = client.post("/api/v1/auth/token/2fa/", {"challenge": first.data["challenge"], "code": "000000"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertTrue(any("may know your password" in m.subject for m in mail.outbox))
        # Even a right code on a fresh challenge waits now.
        client, fresh = self.password_step()
        r = client.post("/api/v1/auth/token/2fa/", {"challenge": fresh.data["challenge"], "code": self.code_now(1)}, format="json")
        self.assertEqual(r.status_code, 429)
        cache.delete(f"2fa-user-failures:{self.user.pk}")
        r = client.post("/api/v1/auth/token/2fa/", {"challenge": fresh.data["challenge"], "code": self.code_now(1)}, format="json")
        self.assertEqual(r.status_code, 200, r.data)

    def test_forged_or_expired_challenge(self):
        self.enable()
        r = APIClient().post("/api/v1/auth/token/2fa/", {"challenge": "x.y.z", "code": self.code_now(1)}, format="json")
        self.assertEqual(r.status_code, 401)
        _, first = self.password_step()
        with mock.patch("django.core.signing.time.time", return_value=__import__("time").time() + 400):
            r = APIClient().post("/api/v1/auth/token/2fa/", {"challenge": first.data["challenge"], "code": self.code_now(1)}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_recovery_code_signs_in_once(self):
        _, codes = self.enable()
        client, first = self.password_step()
        r = client.post("/api/v1/auth/token/2fa/", {"challenge": first.data["challenge"], "code": codes[0].upper()}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["recovery_codes_left"], 9)
        client, first = self.password_step()
        r = client.post("/api/v1/auth/token/2fa/", {"challenge": first.data["challenge"], "code": codes[0]}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_regenerate_and_disable(self):
        _, old = self.enable()
        r = self.client.post("/api/v1/auth/2fa/recovery-codes/", {"password": PASSWORD, "code": old[1]}, format="json")
        self.assertEqual(r.status_code, 200)
        new = r.data["recovery_codes"]
        self.assertFalse(set(new) & set(old))
        bad = self.client.post("/api/v1/auth/2fa/disable/", {"password": PASSWORD, "code": old[2]}, format="json")
        self.assertEqual(bad.status_code, 400)
        nopass = self.client.post("/api/v1/auth/2fa/disable/", {"password": "x", "code": new[0]}, format="json")
        self.assertEqual(nopass.status_code, 400)
        ok = self.client.post("/api/v1/auth/2fa/disable/", {"password": PASSWORD, "code": new[0]}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertFalse(TwoFactorAuth.objects.filter(user=self.user).exists())
        _, response = self.password_step()
        self.assertIn("access", response.data)

    def test_wrong_password_never_reveals_two_factor(self):
        self.enable()
        r = APIClient().post("/api/v1/auth/token/", {"username": "amina", "password": "wrong"}, format="json")
        self.assertEqual(r.status_code, 401)
        self.assertNotIn("two_factor_required", r.data)
