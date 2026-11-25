import time
from unittest import mock

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.social.models import Follow

from . import google
from .models import SocialLogin, UserProfile

User = get_user_model()
CLIENT_ID = "123-test.apps.googleusercontent.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def token(**claims):
    now = int(time.time())
    body = {"iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "g-1001", "email": "neema@gmail.com", "email_verified": True,
            "given_name": "Neema", "family_name": "K", "iat": now, "exp": now + 600, **claims}
    return jwt.encode(body, KEY, algorithm="RS256", headers={"kid": "k1"})


class FakeJwks:
    def get_signing_key_from_jwt(self, _token):
        return mock.Mock(key=KEY.public_key())


@override_settings(GOOGLE_CLIENT_ID=CLIENT_ID)
class GoogleSignInTests(APITestCase):
    def setUp(self):
        patcher = mock.patch.object(google, "_jwks", FakeJwks())
        patcher.start()
        self.addCleanup(patcher.stop)

    def sign_in(self, credential, **extra):
        client = APIClient(enforce_csrf_checks=False)
        return client.post("/api/v1/auth/google/", {"credential": credential, **extra}, format="json")

    def test_new_member_is_created_signed_in_and_confirmed(self):
        response = self.sign_in(token())
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["created"])
        self.assertIn("access", response.data)
        self.assertIn("cg_refresh", response.cookies)
        user = User.objects.get(email="neema@gmail.com")
        self.assertEqual((user.username, user.first_name), ("neema", "Neema"))
        self.assertFalse(user.has_usable_password())
        self.assertIsNotNone(user.profile.email_verified_at)
        again = self.sign_in(token())
        self.assertFalse(again.data["created"], "same Google account, same member")
        self.assertEqual(User.objects.count(), 1)

    def test_existing_confirmed_account_with_same_email_is_linked(self):
        existing = User.objects.create_user("neema_k", "Neema@Gmail.com", "pw-12345-x")
        UserProfile.objects.update_or_create(user=existing, defaults={"email_verified_at": timezone.now()})
        response = self.sign_in(token())
        self.assertFalse(response.data["created"])
        self.assertTrue(SocialLogin.objects.filter(user=existing, uid="g-1001").exists())

    def test_unconfirmed_account_with_same_email_is_not_taken_over(self):
        # Someone registered with this address and never confirmed it: Google must not attach to that account.
        squatter = User.objects.create_user("squatter", "neema@gmail.com", "pw-12345-x")
        response = self.sign_in(token())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "email_unconfirmed")
        self.assertNotIn("access", response.data)
        self.assertFalse(SocialLogin.objects.filter(user=squatter).exists())
        self.assertFalse(UserProfile.objects.filter(user=squatter, email_verified_at__isnull=False).exists())

    def test_google_only_account_can_ask_for_a_password_reset(self):
        self.sign_in(token())
        user = User.objects.get(email="neema@gmail.com")
        self.assertFalse(user.has_usable_password())
        response = APIClient(enforce_csrf_checks=False).post("/api/v1/auth/password/reset/", {"login": "neema@gmail.com"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["neema@gmail.com"])

    def test_bad_tokens_are_refused(self):
        self.assertEqual(self.sign_in(token(aud="someone-else")).status_code, 400)
        self.assertEqual(self.sign_in(token(email_verified=False)).status_code, 400)
        self.assertEqual(self.sign_in(token(iss="https://evil.example.com")).status_code, 400)
        self.assertEqual(self.sign_in(token(exp=int(time.time()) - 3600)).status_code, 400)
        self.assertEqual(self.sign_in("not-a-token").status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    def test_two_step_sign_in_still_applies(self):
        from .models import TwoFactorAuth

        user = User.objects.create_user("neema_k", "neema@gmail.com", "pw-12345-x")
        UserProfile.objects.update_or_create(user=user, defaults={"email_verified_at": timezone.now()})
        TwoFactorAuth.objects.create(user=user, secret_encrypted="x", confirmed_at="2026-01-01T00:00:00Z")
        response = self.sign_in(token())
        self.assertTrue(response.data["two_factor_required"])
        self.assertNotIn("access", response.data)

    def test_invite_and_username_collisions(self):
        inviter = User.objects.create_user("baraka", "b@example.com", "x")
        User.objects.create_user("neema", "other@example.com", "x")
        response = self.sign_in(token(), invited_by="baraka")
        user = User.objects.get(email="neema@gmail.com")
        self.assertEqual(user.username, "neema2")
        self.assertTrue(Follow.objects.filter(follower=user, following=inviter).exists() or Follow.objects.filter(follower=inviter, following=user).exists())
        self.assertEqual(response.status_code, 200)

    def test_providers_endpoint_and_passwordless_delete(self):
        self.assertEqual(self.client.get("/api/v1/auth/providers/").data, {"google_client_id": CLIENT_ID})
        self.sign_in(token())
        user = User.objects.get(email="neema@gmail.com")
        client = APIClient()
        client.force_authenticate(user)
        me = client.get("/api/v1/auth/me/").data
        self.assertEqual((me["has_password"], me["google_linked"]), (False, True))
        self.assertEqual(client.post("/api/v1/auth/account/delete/", {"confirm": "DELETE"}, format="json").status_code, 200)

    @override_settings(GOOGLE_CLIENT_ID="")
    def test_off_without_client_id(self):
        self.assertEqual(self.sign_in(token()).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/auth/providers/").data, {"google_client_id": ""})
