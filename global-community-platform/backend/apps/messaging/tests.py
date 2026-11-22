import hashlib
import secrets
from urllib.parse import urlencode

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.core.cache import cache
from unittest.mock import AsyncMock, patch
from rest_framework.test import APIClient

from config.asgi import application
from .models import Conversation, ConversationMember, Message, MessageReadReceipt
from .auth import consume_cached_ticket, consume_ticket

User = get_user_model()


class WebSocketTicketConsumptionTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def issue_ticket(self, payload, timeout=15):
        ticket = secrets.token_urlsafe(32)
        cache.set(
            f"ws-ticket:{hashlib.sha256(ticket.encode()).hexdigest()}",
            payload,
            timeout,
        )
        return ticket

    def test_expired_ticket_is_rejected(self):
        ticket = self.issue_ticket({"id": 1, "username": "user", "is_active": True}, timeout=0)
        key = f"ws-ticket:{hashlib.sha256(ticket.encode()).hexdigest()}"
        self.assertIsNone(consume_cached_ticket(key))

    def test_ticket_is_single_use(self):
        ticket = self.issue_ticket({"id": 1, "username": "user", "is_active": True})
        key = f"ws-ticket:{hashlib.sha256(ticket.encode()).hexdigest()}"
        first_use = consume_cached_ticket(key)
        replay = consume_cached_ticket(key)
        self.assertEqual(first_use["id"], 1)
        self.assertIsNone(replay)

    def test_stale_inactive_snapshot_does_not_prevent_database_verification(self):
        ticket = self.issue_ticket({"id": 1, "username": "user", "is_active": False})
        key = f"ws-ticket:{hashlib.sha256(ticket.encode()).hexdigest()}"
        self.assertIsNotNone(consume_cached_ticket(key))


class WebSocketTicketAuthenticationTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="ticket-user", password="Test-pass-12345")

    def issue_ticket(self, user_id=None, timeout=15):
        ticket = secrets.token_urlsafe(32)
        cache.set(
            f"ws-ticket:{hashlib.sha256(ticket.encode()).hexdigest()}",
            {"id": user_id or self.user.pk, "username": "untrusted-snapshot", "is_active": True},
            timeout,
        )
        return ticket

    def test_valid_ticket_returns_database_user(self):
        ticket = self.issue_ticket()
        user = async_to_sync(consume_ticket)(ticket)
        self.assertEqual(user.pk, self.user.pk)
        self.assertEqual(user.username, self.user.username)
        self.assertTrue(user.is_active)

    def test_expired_ticket_is_rejected(self):
        ticket = self.issue_ticket(timeout=0)
        self.assertFalse(async_to_sync(consume_ticket)(ticket).is_authenticated)

    def test_reused_ticket_is_rejected(self):
        ticket = self.issue_ticket()
        self.assertTrue(async_to_sync(consume_ticket)(ticket).is_authenticated)
        self.assertFalse(async_to_sync(consume_ticket)(ticket).is_authenticated)

    def test_user_deactivated_after_ticket_issue_is_rejected(self):
        ticket = self.issue_ticket()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertFalse(async_to_sync(consume_ticket)(ticket).is_authenticated)

    def test_deleted_user_is_rejected(self):
        ticket = self.issue_ticket()
        self.user.delete()
        self.assertFalse(async_to_sync(consume_ticket)(ticket).is_authenticated)

    def test_database_verification_failure_fails_closed(self):
        ticket = self.issue_ticket()
        with patch("apps.messaging.auth.consume_ticket_and_get_active_user", new_callable=AsyncMock) as lookup:
            lookup.side_effect = RuntimeError("database unavailable")
            user = async_to_sync(consume_ticket)(ticket)
        self.assertFalse(user.is_authenticated)


class MessagingApiTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.alex = User.objects.create_user(username="alex", password="Test-pass-12345")
        self.bella = User.objects.create_user(username="bella", password="Test-pass-12345")
        self.client = APIClient()
        self.client.force_authenticate(self.alex)

    def test_direct_conversation_is_created_and_reused(self):
        first = self.client.post("/api/v1/conversations/start-direct/", {"user_id": self.bella.id}, format="json")
        second = self.client.post("/api/v1/conversations/start-direct/", {"user_id": self.bella.id}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(Conversation.objects.filter(conversation_type=Conversation.DIRECT).count(), 1)

    def test_group_creation_and_message_persistence(self):
        created = self.client.post("/api/v1/conversations/", {
            "title": "Project team", "member_ids": [self.bella.id],
        }, format="json")
        self.assertEqual(created.status_code, 201)
        conversation_id = created.data["id"]
        sent = self.client.post(f"/api/v1/conversations/{conversation_id}/messages/", {
            "body": "Hello team",
        }, format="json")
        self.assertEqual(sent.status_code, 201)
        self.assertEqual(Message.objects.filter(conversation_id=conversation_id).count(), 1)
        self.assertTrue(MessageReadReceipt.objects.filter(message_id=sent.data["id"], user=self.alex).exists())

    def test_non_member_cannot_view_conversation(self):
        created = self.client.post("/api/v1/conversations/", {
            "title": "Private team", "member_ids": [self.bella.id],
        }, format="json")
        charlie = User.objects.create_user(username="charlie", password="Test-pass-12345")
        outsider = APIClient()
        outsider.force_authenticate(charlie)
        response = outsider.get(f"/api/v1/conversations/{created.data['id']}/messages/")
        self.assertEqual(response.status_code, 404)

    def test_user_search_excludes_current_user(self):
        response = self.client.get("/api/v1/messaging/users/?q=be")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([u["username"] for u in response.data["results"]], ["bella"])


class MessagingWebSocketTests(TransactionTestCase):
    def setUp(self):
        self.alex = User.objects.create_user(username="alex-ws", password="Test-pass-12345")
        self.bella = User.objects.create_user(username="bella-ws", password="Test-pass-12345")
        self.outsider = User.objects.create_user(username="outsider-ws", password="Test-pass-12345")
        self.conversation = Conversation.objects.create(conversation_type=Conversation.DIRECT, created_by=self.alex)
        ConversationMember.objects.create(conversation=self.conversation, user=self.alex, role=ConversationMember.OWNER)
        ConversationMember.objects.create(conversation=self.conversation, user=self.bella)

    def test_jwt_authenticated_socket_can_send_message(self):
        async_to_sync(self._jwt_authenticated_socket_can_send_message)()

    async def _jwt_authenticated_socket_can_send_message(self):
        ticket = self.issue_ticket(self.alex)
        path = f"/ws/chat/{self.conversation.id}/?{urlencode({'ticket': ticket})}"
        communicator = WebsocketCommunicator(application, path, headers=[(b"origin", b"http://localhost")])
        connected = False
        try:
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.send_json_to({"type": "message", "body": "Hello over websocket"})
            events = [await communicator.receive_json_from() for _ in range(2)]
            message_event = next(event for event in events if event["type"] == "message.created")
            self.assertEqual(message_event["message"]["body"], "Hello over websocket")
        finally:
            if connected:
                await communicator.disconnect()
            else:
                await communicator.wait()

    def test_socket_rejects_non_member(self):
        async_to_sync(self._socket_rejects_non_member)()

    async def _socket_rejects_non_member(self):
        ticket = self.issue_ticket(self.outsider)
        path = f"/ws/chat/{self.conversation.id}/?{urlencode({'ticket': ticket})}"
        communicator = WebsocketCommunicator(application, path, headers=[(b"origin", b"http://localhost")])
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.wait()

    def issue_ticket(self, user):
        import secrets
        ticket = secrets.token_urlsafe(32)
        cache.set(
            f"ws-ticket:{hashlib.sha256(ticket.encode()).hexdigest()}",
            {"id": user.pk, "username": user.username, "is_active": user.is_active},
            15,
        )
        return ticket

    def test_ticket_is_one_time_use(self):
        async_to_sync(self._ticket_is_one_time_use)()

    async def _ticket_is_one_time_use(self):
        ticket = self.issue_ticket(self.alex)
        path = f"/ws/chat/{self.conversation.id}/?{urlencode({'ticket': ticket})}"
        first = WebsocketCommunicator(application, path, headers=[(b"origin", b"http://localhost")])
        connected, _ = await first.connect()
        self.assertTrue(connected)
        await first.disconnect()
        second = WebsocketCommunicator(application, path, headers=[(b"origin", b"http://localhost")])
        connected, _ = await second.connect()
        self.assertFalse(connected)
        await second.wait()

    def test_expired_ticket_is_rejected(self):
        async_to_sync(self._expired_ticket_is_rejected)()

    async def _expired_ticket_is_rejected(self):
        ticket = self.issue_ticket(self.alex)
        cache.set(
            f"ws-ticket:{hashlib.sha256(ticket.encode()).hexdigest()}",
            {"id": self.alex.pk, "username": self.alex.username, "is_active": True},
            timeout=0,
        )
        path = f"/ws/chat/{self.conversation.id}/?{urlencode({'ticket': ticket})}"
        communicator = WebsocketCommunicator(application, path, headers=[(b"origin", b"http://localhost")])
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.wait()

    def test_invalid_ticket_is_rejected_before_socket_acceptance(self):
        async_to_sync(self._invalid_ticket_is_rejected_before_socket_acceptance)()

    async def _invalid_ticket_is_rejected_before_socket_acceptance(self):
        path = f"/ws/chat/{self.conversation.id}/?{urlencode({'ticket': 'not-a-valid-ticket'})}"
        communicator = WebsocketCommunicator(application, path, headers=[(b"origin", b"http://localhost")])
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.wait()

    def test_inactive_user_ticket_is_rejected(self):
        self.alex.is_active = False
        self.alex.save(update_fields=["is_active"])
        async_to_sync(self._inactive_user_ticket_is_rejected)()

    async def _inactive_user_ticket_is_rejected(self):
        ticket = self.issue_ticket(self.alex)
        path = f"/ws/chat/{self.conversation.id}/?{urlencode({'ticket': ticket})}"
        communicator = WebsocketCommunicator(application, path, headers=[(b"origin", b"http://localhost")])
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.wait()
