import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.messaging.models import Conversation, ConversationMember, Message
from apps.messaging.services import get_or_create_direct_conversation
from apps.safety.models import Block
from config.asgi import application

from .models import Call
from .services import clean_signal, ice_servers

User = get_user_model()


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class CallFlowTests(APITestCase):
    def setUp(self):
        self.amina = User.objects.create_user("amina", password="x")
        self.juma = User.objects.create_user("juma", password="x")
        self.conversation = get_or_create_direct_conversation(self.amina, self.juma)
        self.a, self.j = client_for(self.amina), client_for(self.juma)

    def start(self, kind="video", client=None):
        return (client or self.a).post("/api/v1/calls/", {"conversation_id": self.conversation.pk, "kind": kind}, format="json")

    def test_call_accept_end_logs_duration_in_chat(self):
        started = self.start()
        self.assertEqual(started.status_code, 201, started.data)
        self.assertEqual(started.data["call"]["status"], "ringing")
        self.assertTrue(started.data["ice_servers"])
        call_id = started.data["call"]["id"]
        self.assertEqual(self.j.get("/api/v1/calls/active/").data["call"]["id"], call_id)

        self.assertEqual(self.a.post(f"/api/v1/calls/{call_id}/accept/", {}, format="json").status_code, 404, "caller can't answer")
        accepted = self.j.post(f"/api/v1/calls/{call_id}/accept/", {"device_id": "tab-1"}, format="json")
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertEqual(accepted.data["call"]["answered_device"], "tab-1")
        self.assertEqual(self.j.post(f"/api/v1/calls/{call_id}/accept/", {}, format="json").status_code, 409, "second tab can't also answer")

        Call.objects.filter(pk=call_id).update(answered_at=timezone.now() - timedelta(seconds=151))
        ended = self.j.post(f"/api/v1/calls/{call_id}/end/", {}, format="json")
        self.assertEqual(ended.data["call"]["status"], "ended")
        message = Message.objects.filter(conversation=self.conversation).latest("id")
        self.assertEqual(message.sender, self.amina)
        self.assertEqual(message.body, "📞 Video call · 2:31")
        self.assertIsNone(self.a.get("/api/v1/calls/active/").data["call"])

    def test_decline_cancel_and_missed(self):
        call_id = self.start("audio").data["call"]["id"]
        self.assertEqual(self.j.post(f"/api/v1/calls/{call_id}/decline/").data["call"]["status"], "declined")
        self.assertEqual(Message.objects.latest("id").body, "📞 Voice call declined")

        call_id = self.start("audio").data["call"]["id"]
        self.assertEqual(self.a.post(f"/api/v1/calls/{call_id}/end/").data["call"]["status"], "cancelled")
        self.assertEqual(Message.objects.latest("id").body, "📞 Missed voice call")

        call_id = self.start("audio").data["call"]["id"]
        Call.objects.filter(pk=call_id).update(created_at=timezone.now() - timedelta(minutes=2))
        self.assertIsNone(self.j.get("/api/v1/calls/active/").data["call"], "unanswered calls expire")
        self.assertEqual(Call.objects.get(pk=call_id).status, "missed")

    def test_busy_blocked_group_and_strangers(self):
        self.assertEqual(self.start().status_code, 201)
        self.assertEqual(self.start().status_code, 409, "already in a call")
        Call.objects.update(status=Call.ENDED)

        Block.objects.create(blocker=self.juma, blocked=self.amina)
        self.assertEqual(self.start().status_code, 403)
        Block.objects.all().delete()

        stranger = User.objects.create_user("stranger", password="x")
        self.assertEqual(self.start(client=client_for(stranger)).status_code, 404)
        group = Conversation.objects.create(conversation_type=Conversation.GROUP, title="Team", created_by=self.amina)
        ConversationMember.objects.create(conversation=group, user=self.amina)
        response = self.a.post("/api/v1/calls/", {"conversation_id": group.pk, "kind": "audio"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.a.post("/api/v1/calls/", {"conversation_id": self.conversation.pk, "kind": "hologram"}, format="json").status_code, 400)

        call_id = self.start().data["call"]["id"]
        self.assertEqual(client_for(stranger).post(f"/api/v1/calls/{call_id}/end/").status_code, 404)

    @override_settings(TURN_URLS=["turn:turn.example.org:3478"], TURN_SECRET="s3cret", TURN_CREDENTIAL_TTL=600)
    def test_turn_credentials_are_short_lived_hmac(self):
        import base64
        import hashlib as h
        import hmac
        import time

        turn = ice_servers(self.amina)[-1]
        expires, user_id = turn["username"].split(":")
        self.assertEqual(user_id, str(self.amina.pk))
        self.assertAlmostEqual(int(expires), int(time.time()) + 600, delta=5)
        expected = base64.b64encode(hmac.new(b"s3cret", turn["username"].encode(), h.sha1).digest()).decode()
        self.assertEqual(turn["credential"], expected)

    @override_settings(TURN_URLS=["turn:standard.relay.metered.ca:80", "turns:standard.relay.metered.ca:443"], TURN_SECRET="", TURN_USERNAME="u123", TURN_CREDENTIAL="c456")
    def test_hosted_turn_with_fixed_credentials(self):
        turn = ice_servers(self.amina)[-1]
        self.assertEqual(turn, {"urls": ["turn:standard.relay.metered.ca:80", "turns:standard.relay.metered.ca:443"], "username": "u123", "credential": "c456"})

    def test_call_data_survives_the_redis_channel_layer_encoding(self):
        # channels_redis serialises events with msgpack, which rejects datetimes.
        import msgpack

        from .services import call_data

        call = Call.objects.create(conversation=self.conversation, caller=self.amina, callee=self.juma, answered_at=timezone.now(), ended_at=timezone.now())
        event = {"type": "call.event", "data": {"type": "call.update", "call": call_data(call)}}
        self.assertEqual(msgpack.unpackb(msgpack.packb(event)), event)

    def test_only_sdp_and_candidates_are_relayed(self):
        self.assertIsNotNone(clean_signal({"sdp": {"type": "offer", "sdp": "v=0"}}))
        self.assertIsNotNone(clean_signal({"candidate": {"candidate": "candidate:1 1 udp 1 1.2.3.4 5 typ host"}}))
        self.assertIsNone(clean_signal({"sdp": {"type": "pranswer", "sdp": "x"}}))
        self.assertIsNone(clean_signal({"html": "<script>"}))
        self.assertIsNone(clean_signal({"candidate": "x" * 70_000}))
        self.assertIsNone(clean_signal("nope"))


def ticket_for(user):
    ticket = secrets.token_urlsafe(32)
    cache.set(f"ws-ticket:{hashlib.sha256(ticket.encode()).hexdigest()}", {"id": user.pk, "username": user.username, "is_active": True}, timeout=15)
    return ticket


class CallSignallingSocketTests(TransactionTestCase):
    def setUp(self):
        self.amina = User.objects.create_user("amina_ws", password="x")
        self.juma = User.objects.create_user("juma_ws", password="x")
        self.eve = User.objects.create_user("eve_ws", password="x")
        conversation = get_or_create_direct_conversation(self.amina, self.juma)
        self.call = Call.objects.create(conversation=conversation, caller=self.amina, callee=self.juma, kind="video")

    def test_starting_a_call_rings_the_callee_socket(self):
        async_to_sync(self._ring)()

    async def _ring(self):
        juma = await self.connect(self.juma)
        try:
            await database_sync_to_async(Call.objects.all().delete)()
            client = APIClient()
            client.force_authenticate(self.amina)
            response = await database_sync_to_async(client.post)("/api/v1/calls/", {"conversation_id": self.call.conversation_id, "kind": "audio"}, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            ring = await juma.receive_json_from(timeout=2)
            self.assertEqual(ring["type"], "call.incoming")
            self.assertEqual(ring["call"]["caller"]["username"], "amina_ws")
            self.assertIsInstance(ring["call"]["created_at"], str)
        finally:
            await juma.disconnect()

    def test_signals_reach_only_the_other_participant_of_an_accepted_call(self):
        async_to_sync(self._relay)()

    async def connect(self, user):
        communicator = WebsocketCommunicator(application, f"/ws/calls/?{urlencode({'ticket': ticket_for(user)})}", headers=[(b"origin", b"http://localhost")])
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        self.assertEqual((await communicator.receive_json_from())["type"], "calls.connected")
        return communicator

    async def _relay(self):
        amina, juma, eve = await self.connect(self.amina), await self.connect(self.juma), await self.connect(self.eve)
        try:
            offer = {"type": "signal", "call_id": self.call.pk, "data": {"sdp": {"type": "offer", "sdp": "v=0"}}}
            await amina.send_json_to(offer)
            refused = await amina.receive_json_from()
            self.assertEqual(refused["type"], "call.error", "ringing calls don't relay yet")

            await database_sync_to_async(Call.objects.filter(pk=self.call.pk).update)(status=Call.ACCEPTED)
            await amina.send_json_to({**offer, "device_id": "a-tab"})
            relayed = await juma.receive_json_from()
            self.assertEqual(relayed["type"], "call.signal")
            self.assertEqual(relayed["data"]["sdp"]["type"], "offer")
            self.assertEqual(relayed["from"], self.amina.pk)

            await eve.send_json_to(offer)
            self.assertEqual((await eve.receive_json_from())["type"], "call.error", "outsiders can't inject signals")
            await amina.send_json_to({"type": "signal", "call_id": self.call.pk, "data": {"evil": 1}})
            self.assertTrue(await juma.receive_nothing(timeout=0.3), "junk is dropped")
            self.assertTrue(await eve.receive_nothing(timeout=0.1))
        finally:
            for communicator in (amina, juma, eve):
                await communicator.disconnect()
