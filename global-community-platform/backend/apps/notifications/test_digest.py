from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.discussions.models import Discussion
from apps.messaging.services import get_or_create_direct_conversation, send_message
from apps.social.models import Follow

from .digest import send_weekly_digests, unsubscribe_link
from .models import NotificationPreference

User = get_user_model()


def member(name, verified=True, days_away=5):
    user = User.objects.create_user(name, f"{name}@example.com", "x", first_name=name.title())
    UserProfile.objects.update_or_create(user=user, defaults={"email_verified_at": timezone.now() if verified else None})
    User.objects.filter(pk=user.pk).update(last_login=timezone.now() - timedelta(days=days_away), date_joined=timezone.now() - timedelta(days=30))
    return User.objects.get(pk=user.pk)


@override_settings(FRONTEND_URL="https://cg.example.com")
class DigestTests(TestCase):
    def setUp(self):
        self.away = member("amina")
        self.friend = member("juma", days_away=0)
        Follow.objects.create(follower=self.friend, following=self.away)
        Follow.objects.create(follower=self.away, following=self.friend)
        Discussion.objects.create(author=self.friend, title="", body="Big news from Dodoma")
        send_message(get_or_create_direct_conversation(self.friend, self.away), self.friend, "hello?")

    def test_inactive_verified_member_gets_one_digest_with_unsubscribe(self):
        self.assertEqual(send_weekly_digests(), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["amina@example.com"])
        self.assertIn("new follower", email.subject)
        body = email.alternatives[0][0]
        self.assertIn("@juma started following you", body)
        self.assertIn("1 unread message", body)
        self.assertIn("Big news from Dodoma", body)
        self.assertIn("https://cg.example.com/api/v1/notifications/digest/unsubscribe/?t=", email.body)
        self.assertIn("List-Unsubscribe", email.extra_headers)
        self.assertEqual(send_weekly_digests(), 0, "once a week at most")

    def test_skips_active_unverified_opted_out_and_people_with_no_news(self):
        User.objects.filter(pk=self.away.pk).update(last_login=timezone.now())
        self.assertEqual(send_weekly_digests(), 0, "recently active")
        User.objects.filter(pk=self.away.pk).update(last_login=timezone.now() - timedelta(days=5))
        UserProfile.objects.filter(user=self.away).update(email_verified_at=None)
        self.assertEqual(send_weekly_digests(), 0, "unconfirmed email")
        UserProfile.objects.filter(user=self.away).update(email_verified_at=timezone.now())
        NotificationPreference.objects.update_or_create(user=self.away, defaults={"email_digest_enabled": False})
        self.assertEqual(send_weekly_digests(), 0, "switched off")
        member("quiet")
        NotificationPreference.objects.filter(user=self.away).update(email_digest_enabled=True)
        self.assertEqual(send_weekly_digests(), 1, "only amina has news; 'quiet' has none")

    def test_daily_limit(self):
        for i in range(3):
            other = member(f"reader{i}")
            Follow.objects.create(follower=self.friend, following=other)
        self.assertEqual(send_weekly_digests(limit=2), 2)
        self.assertEqual(send_weekly_digests(limit=2), 2, "the rest go out next run")

    def test_one_click_unsubscribe(self):
        link = unsubscribe_link(self.away).replace("https://cg.example.com", "")
        self.assertEqual(self.client.post(link).status_code, 200)
        self.assertFalse(NotificationPreference.objects.get(user=self.away).email_digest_enabled)
        self.assertEqual(self.client.get(link[:-4] + "abcd").status_code, 400)
        self.assertEqual(send_weekly_digests(), 0)
