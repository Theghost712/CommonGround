from datetime import timedelta
from urllib.parse import urlencode

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.messaging.models import Conversation, ConversationMember, Message
from apps.messaging.services import get_or_create_direct_conversation
from config.asgi import application

from .group import expire_stale_group_calls
from .models import Call, GroupCall, GroupCallParticipant
from .tests import ticket_for

User = get_user_model()


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def make_group(owner, *members, title="Book club"):
    conversation = Conversation.objects.create(conversation_type=Conversation.GROUP, title=title, created_by=owner)
    for user in (owner, *members):
        ConversationMember.objects.create(conversation=conversation, user=user)
    return conversation


class GroupCallFlowTests(APITestCase):
    def setUp(self):
        self.amina, self.juma, self.neema, self.eve = (User.objects.create_user(name, password="x") for name in ("amina", "juma", "neema", "eve"))
        self.group = make_group(self.amina, self.juma, self.neema)

    def start(self, user, kind="video", device="tab", conversation=None):
        return client_for(user).post("/api/v1/calls/group/", {"conversation_id": (conversation or self.group).pk, "kind": kind, "device_id": device}, format="json")

    def test_start_join_leave_and_end_logs_in_chat(self):
        started = self.start(self.amina, device="a1")
        self.assertEqual(started.status_code, 201, started.data)
        call = started.data["call"]
        self.assertEqual(call["kind"], "video")
        self.assertEqual([p["username"] for p in call["participants"]], ["amina"])
        self.assertTrue(started.data["ice_servers"])

        joined = self.start(self.juma, kind="audio", device="j1")
        self.assertEqual(joined.status_code, 200, joined.data)
        self.assertEqual(joined.data["call"]["id"], call["id"], "joins the running call")
        self.assertEqual(joined.data["call"]["kind"], "video", "the first person picks the kind")
        self.assertEqual([p["username"] for p in joined.data["call"]["participants"]], ["amina", "juma"])

        active = client_for(self.neema).get("/api/v1/calls/group/active/").data["calls"]
        self.assertEqual([c["id"] for c in active], [call["id"]], "members see the live call to join")
        self.assertEqual(client_for(self.eve).get("/api/v1/calls/group/active/").data["calls"], [], "outsiders don't")

        left = client_for(self.amina).post(f"/api/v1/calls/group/{call['id']}/leave/", {"device_id": "a1"}, format="json")
        self.assertEqual([p["username"] for p in left.data["call"]["participants"]], ["juma"])
        self.assertEqual(left.data["call"]["status"], "live", "the call goes on while someone is in it")

        GroupCall.objects.filter(pk=call["id"]).update(created_at=timezone.now() - timedelta(seconds=125))
        client_for(self.juma).post(f"/api/v1/calls/group/{call['id']}/leave/", {"device_id": "j1"}, format="json")
        self.assertEqual(GroupCall.objects.get(pk=call["id"]).status, GroupCall.ENDED)
        line = Message.objects.filter(conversation=self.group).latest("id")
        self.assertEqual(line.body, "📞 Group video call · 2:05")

    def test_only_group_members_in_group_chats(self):
        self.assertEqual(self.start(self.eve).status_code, 404)
        direct = get_or_create_direct_conversation(self.amina, self.juma)
        self.assertEqual(self.start(self.amina, conversation=direct).status_code, 400)
        self.assertEqual(client_for(self.amina).post("/api/v1/calls/group/", {"conversation_id": self.group.pk, "kind": "screen"}, format="json").status_code, 400)

    @override_settings(GROUP_CALL_MAX_PARTICIPANTS=2)
    def test_call_is_capped(self):
        self.start(self.amina)
        self.start(self.juma)
        full = self.start(self.neema)
        self.assertEqual(full.status_code, 409)
        self.assertIn("full", full.data["detail"])

    def test_busy_rules_between_one_to_one_and_group_calls(self):
        direct = get_or_create_direct_conversation(self.juma, self.eve)
        Call.objects.create(conversation=direct, caller=self.juma, callee=self.eve, status=Call.ACCEPTED, answered_at=timezone.now())
        self.assertEqual(self.start(self.juma).status_code, 409, "can't join a group call during a 1:1 call")

        self.start(self.amina)
        other = make_group(self.amina, self.neema, title="Other")
        self.assertEqual(self.start(self.amina, conversation=other).status_code, 409, "one group call at a time")
        dm = get_or_create_direct_conversation(self.neema, self.amina)
        ring = client_for(self.neema).post("/api/v1/calls/", {"conversation_id": dm.pk, "kind": "audio"}, format="json")
        self.assertEqual(ring.status_code, 409, "people in a group call aren't rung for 1:1 calls")

    def test_second_device_takes_over_and_old_tab_cannot_hang_up(self):
        call_id = self.start(self.amina, device="phone").data["call"]["id"]
        self.start(self.juma)
        self.start(self.amina, device="laptop")
        seat = GroupCallParticipant.objects.get(call_id=call_id, user=self.amina, left_at__isnull=True)
        self.assertEqual(seat.device_id, "laptop")
        client_for(self.amina).post(f"/api/v1/calls/group/{call_id}/leave/", {"device_id": "phone"}, format="json")
        self.assertTrue(GroupCallParticipant.objects.filter(pk=seat.pk, left_at__isnull=True).exists())
        beat = client_for(self.amina).post(f"/api/v1/calls/group/{call_id}/heartbeat/", {"device_id": "phone"}, format="json")
        self.assertEqual(beat.status_code, 410, "the replaced tab learns it's out")
        self.assertEqual(client_for(self.amina).post(f"/api/v1/calls/group/{call_id}/heartbeat/", {"device_id": "laptop"}, format="json").status_code, 200)

    def test_silent_participants_are_dropped_and_empty_calls_end(self):
        call_id = self.start(self.amina, device="a").data["call"]["id"]
        self.start(self.juma, device="j")
        GroupCallParticipant.objects.filter(user=self.amina).update(last_seen=timezone.now() - timedelta(minutes=2))
        expire_stale_group_calls()
        self.assertEqual(list(GroupCallParticipant.objects.filter(call_id=call_id, left_at__isnull=True).values_list("user__username", flat=True)), ["juma"])
        GroupCallParticipant.objects.filter(user=self.juma).update(last_seen=timezone.now() - timedelta(minutes=2))
        expire_stale_group_calls()
        self.assertEqual(GroupCall.objects.get(pk=call_id).status, GroupCall.ENDED)
        # A new call can start in the same chat afterwards.
        self.assertEqual(self.start(self.neema).status_code, 201)


class GroupCallSocketTests(TransactionTestCase):
    def setUp(self):
        self.amina, self.juma, self.neema, self.eve = (User.objects.create_user(f"{name}_gws", password="x") for name in ("amina", "juma", "neema", "eve"))
        self.group = make_group(self.amina, self.juma, self.neema, self.eve)
        self.call = GroupCall.objects.create(conversation=self.group, started_by=self.amina, kind="video")
        GroupCallParticipant.objects.create(call=self.call, user=self.amina, device_id="a-tab")
        GroupCallParticipant.objects.create(call=self.call, user=self.juma, device_id="j-tab")

    async def connect(self, user):
        communicator = WebsocketCommunicator(application, f"/ws/calls/?{urlencode({'ticket': ticket_for(user)})}", headers=[(b"origin", b"http://localhost")])
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        self.assertEqual((await communicator.receive_json_from())["type"], "calls.connected")
        return communicator

    def test_group_signals_go_only_between_participants(self):
        async_to_sync(self._relay)()

    async def _relay(self):
        amina, juma, eve = await self.connect(self.amina), await self.connect(self.juma), await self.connect(self.eve)
        offer = {"type": "group_signal", "group_call_id": self.call.pk, "data": {"sdp": {"type": "offer", "sdp": "v=0"}}}
        try:
            await amina.send_json_to({**offer, "to": self.juma.pk, "device_id": "a-tab"})
            relayed = await juma.receive_json_from()
            self.assertEqual(relayed["type"], "group_call.signal")
            self.assertEqual((relayed["from"], relayed["to_device"]), (self.amina.pk, "j-tab"))

            await eve.send_json_to({**offer, "to": self.juma.pk, "device_id": "x"})
            self.assertEqual((await eve.receive_json_from())["type"], "group_call.error", "non-participants can't signal")
            await amina.send_json_to({**offer, "to": self.eve.pk, "device_id": "a-tab"})
            self.assertEqual((await amina.receive_json_from())["type"], "group_call.error", "can't signal people outside the call")
            await amina.send_json_to({**offer, "to": self.juma.pk, "device_id": "other-tab"})
            self.assertEqual((await amina.receive_json_from())["type"], "group_call.error", "only the tab that joined may signal")
            self.assertTrue(await juma.receive_nothing(timeout=0.3))
            self.assertTrue(await eve.receive_nothing(timeout=0.1))
        finally:
            for communicator in (amina, juma, eve):
                await communicator.disconnect()

    def test_members_hear_when_a_call_starts(self):
        async_to_sync(self._started)()

    async def _started(self):
        await database_sync_to_async(GroupCall.objects.all().delete)()
        neema = await self.connect(self.neema)
        try:
            response = await database_sync_to_async(client_for(self.amina).post)(
                "/api/v1/calls/group/", {"conversation_id": self.group.pk, "kind": "audio", "device_id": "a"}, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            event = await neema.receive_json_from(timeout=2)
            self.assertEqual(event["type"], "group_call.started")
            self.assertEqual(event["call"]["started_by"]["username"], "amina_gws")
        finally:
            await neema.disconnect()
