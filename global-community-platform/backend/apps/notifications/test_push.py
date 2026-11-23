from unittest import mock

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import Notification, PushSubscription
from .services import create_notification

User = get_user_model()
FCM = "https://fcm.googleapis.com/fcm/send/abc123"
KEYS = {"p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM", "auth": "tBHItJI5svbpez7KI4CCXg"}
PUSH_ON = dict(VAPID_PUBLIC_KEY="pub", VAPID_PRIVATE_KEY="priv", VAPID_SUBJECT="mailto:t@example.com", WEB_PUSH_SYNC=True)


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code
        self.text = ""


@override_settings(**PUSH_ON)
class PushTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("amina", "a@example.com", "pass-12345-x")
        self.other = User.objects.create_user("baraka", "b@example.com", "pass-12345-x")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def subscribe(self, endpoint=FCM, client=None):
        return (client or self.client).post("/api/v1/push/subscriptions/", {"endpoint": endpoint, "keys": KEYS}, format="json")

    def test_config(self):
        r = self.client.get("/api/v1/push/config/")
        self.assertEqual((r.data["enabled"], r.data["public_key"]), (True, "pub"))
        with override_settings(VAPID_PUBLIC_KEY=""):
            self.assertFalse(self.client.get("/api/v1/push/config/").data["enabled"])
            self.assertEqual(self.subscribe().status_code, 503)

    def test_subscribe_validates_endpoint_and_moves_between_accounts(self):
        self.assertEqual(self.subscribe("https://evil.example.com/x").status_code, 400)
        self.assertEqual(self.subscribe("http://fcm.googleapis.com/x").status_code, 400)
        self.assertEqual(self.subscribe().status_code, 201)
        self.assertEqual(self.subscribe().status_code, 201)
        self.assertEqual(PushSubscription.objects.count(), 1)
        other = APIClient(); other.force_authenticate(self.other)
        self.subscribe(client=other)
        self.assertEqual(PushSubscription.objects.get().user, self.other)
        # Removing someone else's endpoint does nothing.
        self.assertFalse(self.client.post("/api/v1/push/subscriptions/remove/", {"endpoint": FCM}, format="json").data["removed"])
        self.assertTrue(other.post("/api/v1/push/subscriptions/remove/", {"endpoint": FCM}, format="json").data["removed"])

    def test_notification_is_pushed_and_respects_preferences(self):
        self.subscribe()
        with mock.patch("pywebpush.webpush") as webpush, self.captureOnCommitCallbacks(execute=True):
            create_notification(self.user, Notification.MESSAGE, "New message from baraka", "hello", "/messages?conversation=7",
                                actor=self.other, data={"conversation_id": 7})
        self.assertEqual(webpush.call_count, 1)
        import json
        payload = json.loads(webpush.call_args.kwargs["data"])
        self.assertEqual((payload["title"], payload["url"], payload["tag"]), ("New message from baraka", "/messages?conversation=7", "chat-7"))
        self.assertEqual(webpush.call_args.kwargs["subscription_info"]["endpoint"], FCM)

        self.user.notification_preferences.messages_enabled = False
        self.user.notification_preferences.save()
        with mock.patch("pywebpush.webpush") as webpush, self.captureOnCommitCallbacks(execute=True):
            create_notification(self.user, Notification.MESSAGE, "x", actor=self.other)
        webpush.assert_not_called()

    def test_gone_subscription_is_deleted(self):
        from pywebpush import WebPushException

        self.subscribe()
        error = WebPushException("gone", response=FakeResponse(410))
        with mock.patch("pywebpush.webpush", side_effect=error), self.captureOnCommitCallbacks(execute=True):
            create_notification(self.user, Notification.SYSTEM, "hi")
        self.assertFalse(PushSubscription.objects.exists())

    def test_repeated_failures_drop_subscription(self):
        from pywebpush import WebPushException

        self.subscribe()
        error = WebPushException("boom", response=FakeResponse(500))
        with mock.patch("pywebpush.webpush", side_effect=error):
            for _ in range(5):
                with self.captureOnCommitCallbacks(execute=True):
                    create_notification(self.user, Notification.SYSTEM, "hi")
        self.assertFalse(PushSubscription.objects.exists())

    def test_test_endpoint(self):
        self.assertEqual(self.client.post("/api/v1/push/test/").status_code, 400)
        self.subscribe()
        with mock.patch("pywebpush.webpush") as webpush, self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post("/api/v1/push/test/").status_code, 200)
        self.assertEqual(webpush.call_count, 1)

    def test_no_keys_means_no_push(self):
        self.subscribe()
        with override_settings(VAPID_PRIVATE_KEY=""), mock.patch("pywebpush.webpush") as webpush, self.captureOnCommitCallbacks(execute=True):
            create_notification(self.user, Notification.SYSTEM, "hi")
        webpush.assert_not_called()
