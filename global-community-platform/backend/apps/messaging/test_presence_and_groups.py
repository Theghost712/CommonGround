from urllib.parse import urlencode

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from rest_framework import status
from rest_framework.test import APIClient

from config.asgi import application

from .models import Conversation, ConversationMember, UserPresence

User = get_user_model()
ORIGIN = [(b"origin", b"http://localhost")]


def issue_ticket(user):
    client = APIClient()
    client.force_authenticate(user)
    return client.post("/api/v1/auth/ws-ticket/").data["ticket"]


class PresenceSocketTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="present", password="Strong-password-123")

    def socket(self, ticket=None):
        query = f"?{urlencode({'ticket': ticket})}" if ticket else ""
        return WebsocketCommunicator(application, f"/ws/presence/{query}", headers=ORIGIN)

    def test_unauthenticated_presence_connection_is_rejected(self):
        async def scenario():
            communicator = self.socket()
            connected, code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(code, 4401)

        async_to_sync(scenario)()

    def test_connect_sends_snapshot_and_marks_user_online_then_offline(self):
        ticket = issue_ticket(self.user)

        async def scenario():
            communicator = self.socket(ticket)
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            snapshot = await communicator.receive_json_from()
            connected_event = await communicator.receive_json_from()
            self.assertEqual(snapshot["type"], "presence.snapshot")
            self.assertIn(
                {"user_id": self.user.id, "username": "present", "status": "online", "last_seen": None},
                snapshot["presences"],
            )
            self.assertEqual(connected_event, {"type": "presence.connected", "user_id": self.user.id, "status": "online"})

            await communicator.send_json_to({"type": "ping"})
            # A presence.update broadcast for this user may arrive before the pong.
            replies = [await communicator.receive_json_from() for _ in range(2)]
            self.assertIn({"type": "pong"}, replies)
            await communicator.disconnect()

        async_to_sync(scenario)()

        presence = UserPresence.objects.get(user=self.user)
        self.assertFalse(presence.is_online)
        self.assertEqual(presence.active_connections, 0)
        self.assertIsNotNone(presence.last_seen)

    def test_user_stays_online_while_another_tab_is_connected(self):
        first_ticket, second_ticket = issue_ticket(self.user), issue_ticket(self.user)

        load_presence = database_sync_to_async(lambda: UserPresence.objects.get(user=self.user))

        async def scenario():
            first, second = self.socket(first_ticket), self.socket(second_ticket)
            self.assertTrue((await first.connect())[0])
            self.assertTrue((await second.connect())[0])
            await first.disconnect()
            presence = await load_presence()
            self.assertTrue(presence.is_online)
            self.assertEqual(presence.active_connections, 1)
            await second.disconnect()
            presence = await load_presence()
            self.assertFalse(presence.is_online)

        async_to_sync(scenario)()


class GroupMembershipTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="group_owner", password="Strong-password-123")
        self.member = User.objects.create_user(username="group_member", password="Strong-password-123")
        self.newcomer = User.objects.create_user(username="group_newcomer", password="Strong-password-123")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            "/api/v1/conversations/", {"title": "Planning", "member_ids": [self.member.id]}, format="json"
        )
        self.conversation = Conversation.objects.get(pk=response.data["id"])

    def test_group_creation_requires_title_and_participants(self):
        no_title = self.client.post("/api/v1/conversations/", {"title": " ", "member_ids": [self.member.id]}, format="json")
        no_members = self.client.post("/api/v1/conversations/", {"title": "Solo", "member_ids": [self.owner.id]}, format="json")

        self.assertEqual(no_title.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(no_members.status_code, status.HTTP_400_BAD_REQUEST)

    def test_owner_can_add_and_remove_participants(self):
        added = self.client.post(
            f"/api/v1/conversations/{self.conversation.id}/add-members/", {"member_ids": [self.newcomer.id]}, format="json"
        )
        removed = self.client.post(
            f"/api/v1/conversations/{self.conversation.id}/remove-member/", {"user_id": self.member.id}, format="json"
        )

        self.assertEqual(added.data["added"], ["group_newcomer"])
        self.assertEqual(removed.status_code, status.HTTP_200_OK)
        self.assertFalse(ConversationMember.objects.get(conversation=self.conversation, user=self.member).is_active)

    def test_removed_participant_loses_access(self):
        self.client.post(f"/api/v1/conversations/{self.conversation.id}/remove-member/", {"user_id": self.member.id}, format="json")

        member_client = APIClient()
        member_client.force_authenticate(self.member)
        response = member_client.get(f"/api/v1/conversations/{self.conversation.id}/messages/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_regular_member_cannot_manage_participants(self):
        member_client = APIClient()
        member_client.force_authenticate(self.member)

        response = member_client.post(
            f"/api/v1/conversations/{self.conversation.id}/add-members/", {"member_ids": [self.newcomer.id]}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_cannot_be_removed(self):
        ConversationMember.objects.filter(conversation=self.conversation, user=self.member).update(role=ConversationMember.ADMIN)
        admin_client = APIClient()
        admin_client.force_authenticate(self.member)

        response = admin_client.post(
            f"/api/v1/conversations/{self.conversation.id}/remove-member/", {"user_id": self.owner.id}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rest_message_updates_unread_count_until_marked_read(self):
        self.client.post(f"/api/v1/conversations/{self.conversation.id}/messages/", {"body": "Hello team"}, format="json")
        member_client = APIClient()
        member_client.force_authenticate(self.member)

        before = member_client.get(f"/api/v1/conversations/{self.conversation.id}/").data["unread_count"]
        member_client.post(f"/api/v1/conversations/{self.conversation.id}/mark-read/")
        after = member_client.get(f"/api/v1/conversations/{self.conversation.id}/").data["unread_count"]

        self.assertEqual((before, after), (1, 0))


class LeaveGroupTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="leave_owner", password="Strong-password-123")
        self.first = User.objects.create_user(username="leave_first", password="Strong-password-123")
        self.second = User.objects.create_user(username="leave_second", password="Strong-password-123")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            "/api/v1/conversations/", {"title": "Leavers", "member_ids": [self.first.id, self.second.id]}, format="json"
        )
        self.conversation = Conversation.objects.get(pk=response.data["id"])

    def as_user(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_member_can_leave_and_loses_access(self):
        member = self.as_user(self.first)
        response = member.post(f"/api/v1/conversations/{self.conversation.id}/leave/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["new_owner_id"])
        self.assertFalse(ConversationMember.objects.get(conversation=self.conversation, user=self.first).is_active)
        self.assertEqual(member.get(f"/api/v1/conversations/{self.conversation.id}/").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            ConversationMember.objects.get(conversation=self.conversation, user=self.owner).role, ConversationMember.OWNER
        )

    def test_owner_leaving_hands_ownership_to_an_admin_first(self):
        ConversationMember.objects.filter(conversation=self.conversation, user=self.second).update(role=ConversationMember.ADMIN)

        response = self.client.post(f"/api/v1/conversations/{self.conversation.id}/leave/")

        self.assertEqual(response.data["new_owner_id"], self.second.id)
        roles = dict(ConversationMember.objects.filter(conversation=self.conversation).values_list("user__username", "role"))
        self.assertEqual(roles["leave_second"], ConversationMember.OWNER)
        self.assertEqual(roles["leave_owner"], ConversationMember.MEMBER)

    def test_owner_leaving_without_admins_hands_ownership_to_oldest_member(self):
        response = self.client.post(f"/api/v1/conversations/{self.conversation.id}/leave/")

        self.assertIn(response.data["new_owner_id"], {self.first.id, self.second.id})
        self.assertEqual(
            ConversationMember.objects.filter(
                conversation=self.conversation, is_active=True, role=ConversationMember.OWNER
            ).count(),
            1,
        )

    def test_cannot_leave_direct_conversation(self):
        direct = self.client.post("/api/v1/conversations/start-direct/", {"user_id": self.first.id}, format="json").data

        response = self.client.post(f"/api/v1/conversations/{direct['id']}/leave/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejoining_after_leaving_restores_access(self):
        self.as_user(self.first).post(f"/api/v1/conversations/{self.conversation.id}/leave/")

        added = self.client.post(
            f"/api/v1/conversations/{self.conversation.id}/add-members/", {"member_ids": [self.first.id]}, format="json"
        )

        self.assertEqual(added.data["added"], ["leave_first"])
        self.assertEqual(self.as_user(self.first).get(f"/api/v1/conversations/{self.conversation.id}/").status_code, status.HTTP_200_OK)
