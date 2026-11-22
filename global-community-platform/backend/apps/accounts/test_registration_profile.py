from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from .models import UserProfile

User = get_user_model()


class RegistrationTests(APITestCase):
    url = "/api/v1/auth/register/"

    def payload(self, **overrides):
        data = {
            "username": "newmember",
            "email": "newmember@example.test",
            "first_name": "New",
            "last_name": "Member",
            "password": "Strong-password-123",
            "password_confirm": "Strong-password-123",
        }
        data.update(overrides)
        return data

    def test_registration_creates_user_with_hashed_password_and_profile(self):
        response = self.client.post(self.url, self.payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn("password", response.data)
        user = User.objects.get(username="newmember")
        self.assertTrue(user.check_password("Strong-password-123"))
        self.assertNotEqual(user.password, "Strong-password-123")
        self.assertTrue(UserProfile.objects.filter(user=user).exists())

    def test_registration_rejects_mismatched_passwords(self):
        response = self.client.post(self.url, self.payload(password_confirm="Different-password-123"), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)
        self.assertFalse(User.objects.filter(username="newmember").exists())

    def test_registration_rejects_weak_password(self):
        response = self.client.post(self.url, self.payload(password="12345678", password_confirm="12345678"), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_registration_rejects_duplicate_username(self):
        User.objects.create_user(username="newmember", password="Strong-password-123")

        response = self.client.post(self.url, self.payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)


class ProfileTests(APITestCase):
    url = "/api/v1/auth/profile/"

    def setUp(self):
        self.user = User.objects.create_user(
            username="profile_user", email="profile@example.test", password="Strong-password-123"
        )
        self.client.force_authenticate(self.user)

    def test_profile_is_created_lazily_for_existing_accounts(self):
        self.assertFalse(UserProfile.objects.filter(user=self.user).exists())

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "profile_user")
        self.assertEqual(response.data["preferred_language"], "en")
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())

    def test_profile_update_changes_profile_and_user_name_fields(self):
        response = self.client.patch(self.url, {
            "first_name": "Amani",
            "last_name": "Juma",
            "bio": "I like community building.",
            "country": "Tanzania",
            "preferred_language": "sw",
            "website": "https://example.test",
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name), ("Amani", "Juma"))
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.country, "Tanzania")
        self.assertEqual(profile.preferred_language, "sw")

    def test_username_and_email_are_read_only_through_profile(self):
        self.client.patch(self.url, {"username": "hijacked", "email": "other@example.test"}, format="json")

        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "profile_user")
        self.assertEqual(self.user.email, "profile@example.test")

    def test_profile_rejects_invalid_language_and_url(self):
        response = self.client.patch(self.url, {"preferred_language": "xx", "website": "not a url"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("preferred_language", response.data)
        self.assertIn("website", response.data)

    def test_profile_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
