import hashlib
import secrets
from urllib.parse import urlencode

from channels.testing import WebsocketCommunicator
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase
from django.test import TransactionTestCase

from config.asgi import application
from .models import Notification, NotificationPreference
from .services import create_notification

User = get_user_model()


class NotificationApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="notify_user", password="Strong-password-123")
        self.other = User.objects.create_user(username="sender", password="Strong-password-123")
        self.client.force_authenticate(self.user)

    def test_list_only_returns_current_users_notifications(self):
        own = Notification.objects.create(recipient=self.user, title="For me", notification_type=Notification.SYSTEM)
        Notification.objects.create(recipient=self.other, title="Not for me", notification_type=Notification.SYSTEM)
        response = self.client.get("/api/v1/notifications/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual([item["id"] for item in results], [own.id])

    def test_unread_count_and_mark_read(self):
        item = Notification.objects.create(recipient=self.user, title="Unread", notification_type=Notification.SYSTEM)
        count_response = self.client.get("/api/v1/notifications/unread-count/")
        self.assertEqual(count_response.data["unread_count"], 1)
        mark_response = self.client.post(f"/api/v1/notifications/{item.id}/mark-read/")
        self.assertEqual(mark_response.status_code, status.HTTP_200_OK)
        self.assertEqual(mark_response.data["unread_count"], 0)
        item.refresh_from_db()
        self.assertTrue(item.is_read)

    def test_mark_all_read(self):
        Notification.objects.create(recipient=self.user, title="One", notification_type=Notification.SYSTEM)
        Notification.objects.create(recipient=self.user, title="Two", notification_type=Notification.SYSTEM)
        response = self.client.post("/api/v1/notifications/mark-all-read/")
        self.assertEqual(response.data["marked_read"], 2)
        self.assertEqual(Notification.objects.filter(recipient=self.user, is_read=False).count(), 0)

    def test_preferences_can_disable_message_notifications(self):
        preferences, _ = NotificationPreference.objects.get_or_create(user=self.user)
        preferences.messages_enabled = False
        preferences.save()
        result = create_notification(
            recipient=self.user,
            actor=self.other,
            notification_type=Notification.MESSAGE,
            title="A new message",
        )
        self.assertIsNone(result)
        self.assertFalse(Notification.objects.filter(recipient=self.user).exists())

    def test_user_cannot_delete_another_users_notification(self):
        foreign = Notification.objects.create(recipient=self.other, title="Private", notification_type=Notification.SYSTEM)
        response = self.client.delete(f"/api/v1/notifications/{foreign.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class NotificationWebSocketTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="notify-ws", password="Strong-password-123")

    def test_authenticated_user_can_connect_to_notification_socket(self):
        async_to_sync(self._authenticated_user_can_connect_to_notification_socket)()

    async def _authenticated_user_can_connect_to_notification_socket(self):
        ticket = secrets.token_urlsafe(32)
        cache.set(
            f"ws-ticket:{hashlib.sha256(ticket.encode()).hexdigest()}",
            {"id": self.user.pk, "username": self.user.username, "is_active": True},
            timeout=15,
        )
        path = f"/ws/notifications/?{urlencode({'ticket': ticket})}"
        communicator = WebsocketCommunicator(application, path, headers=[(b"origin", b"http://localhost")])
        connected = False
        try:
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            event = await communicator.receive_json_from()
            self.assertEqual(event["type"], "notifications.connected")
            await get_channel_layer().group_send(
                f"notifications_user_{self.user.pk}",
                {"type": "notification.event", "data": {"type": "notification.new", "notification": {"id": 17}}},
            )
            delivered = await communicator.receive_json_from()
            self.assertEqual(delivered["type"], "notification.new")
            self.assertEqual(delivered["notification"]["id"], 17)
        finally:
            if connected:
                await communicator.disconnect()
            else:
                await communicator.wait()

    def test_unauthenticated_connection_is_rejected(self):
        async_to_sync(self._unauthenticated_connection_is_rejected)()

    async def _unauthenticated_connection_is_rejected(self):
        communicator = WebsocketCommunicator(
            application,
            "/ws/notifications/?ticket=invalid",
            headers=[(b"origin", b"http://localhost")],
        )
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.wait()


class LiveDeliveryFromHttpRequestTests(TransactionTestCase):
    """The real path: a normal (sync) HTTP request creates a notification that must reach an open socket."""

    def setUp(self):
        self.recipient = User.objects.create_user(username="live-recipient", password="Strong-password-123")
        self.actor = User.objects.create_user(username="live-actor", password="Strong-password-123")

    def test_follow_request_pushes_notification_to_open_socket(self):
        async_to_sync(self._scenario)()

    async def _scenario(self):
        from asgiref.sync import sync_to_async
        from rest_framework.test import APIClient

        ticket = secrets.token_urlsafe(32)
        cache.set(f"ws-ticket:{hashlib.sha256(ticket.encode()).hexdigest()}", {"id": self.recipient.pk}, timeout=15)
        communicator = WebsocketCommunicator(application, f"/ws/notifications/?{urlencode({'ticket': ticket})}", headers=[(b"origin", b"http://localhost")])
        connected, _ = await communicator.connect()
        try:
            self.assertTrue(connected)
            await communicator.receive_json_from()  # notifications.connected

            def follow():
                client = APIClient()
                client.force_authenticate(self.actor)
                return client.post(f"/api/v1/people/{self.recipient.username}/follow/").status_code

            self.assertEqual(await sync_to_async(follow, thread_sensitive=True)(), 201)
            delivered = await communicator.receive_json_from(timeout=3)
            self.assertEqual(delivered["type"], "notification.new")
            self.assertEqual(delivered["notification"]["notification_type"], "follow")
            self.assertEqual(delivered["unread_count"], 1)
        finally:
            await communicator.disconnect()
