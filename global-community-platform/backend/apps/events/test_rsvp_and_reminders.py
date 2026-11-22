from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.communities.models import Community, CommunityMembership
from apps.notifications.models import Notification

from .models import CommunityEvent, EventReminder, EventRSVP

User = get_user_model()


def make_community(owner, **extra):
    community = Community.objects.create(
        name=extra.pop("name", "Events hub"),
        description="Community for event tests",
        created_by=owner,
        approval_status=Community.APPROVED,
        **extra,
    )
    CommunityMembership.objects.create(
        community=community, user=owner, role=CommunityMembership.OWNER, status=CommunityMembership.ACTIVE
    )
    return community


def make_event(community, creator, starts_in=timedelta(days=2), **extra):
    starts_at = timezone.now() + starts_in
    return CommunityEvent.objects.create(
        community=community,
        created_by=creator,
        title=extra.pop("title", "Monthly meetup"),
        description="Let's meet.",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=2),
        **extra,
    )


class EventRSVPTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="event_owner", password="Strong-password-123")
        self.member = User.objects.create_user(username="event_member", password="Strong-password-123")
        self.outsider = User.objects.create_user(username="event_outsider", password="Strong-password-123")
        self.community = make_community(self.owner)
        CommunityMembership.objects.create(community=self.community, user=self.member)
        self.event = make_event(self.community, self.owner)

    def rsvp(self, user, response):
        self.client.force_authenticate(user)
        return self.client.post(f"/api/v1/events/{self.event.id}/rsvp/", {"response": response}, format="json")

    def test_member_rsvp_is_created_then_updated(self):
        first = self.rsvp(self.member, EventRSVP.GOING)
        second = self.rsvp(self.member, EventRSVP.INTERESTED)

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(EventRSVP.objects.get(event=self.event, user=self.member).response, EventRSVP.INTERESTED)

        detail = self.client.get(f"/api/v1/events/{self.event.id}/")
        self.assertEqual(detail.data["my_response"], EventRSVP.INTERESTED)
        self.assertEqual(detail.data["rsvp_counts"], {"going": 0, "interested": 1, "not_going": 0})

    def test_rsvp_notifies_event_creator_only_when_response_changes(self):
        self.rsvp(self.member, EventRSVP.GOING)
        self.rsvp(self.member, EventRSVP.GOING)

        notifications = Notification.objects.filter(recipient=self.owner, notification_type=Notification.EVENT_RSVP)
        self.assertEqual(notifications.count(), 1)
        self.assertEqual(notifications.get().actor, self.member)

    def test_non_member_cannot_rsvp_to_public_community_event(self):
        response = self.rsvp(self.outsider, EventRSVP.GOING)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(EventRSVP.objects.filter(user=self.outsider).exists())

    def test_invalid_rsvp_response_is_rejected(self):
        response = self.rsvp(self.member, "maybe")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_rsvp_to_cancelled_event(self):
        self.event.status = CommunityEvent.CANCELLED
        self.event.save()

        response = self.rsvp(self.member, EventRSVP.GOING)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_manager_cancel_notifies_members_and_is_idempotent(self):
        self.client.force_authenticate(self.owner)

        first = self.client.post(f"/api/v1/events/{self.event.id}/cancel/")
        second = self.client.post(f"/api/v1/events/{self.event.id}/cancel/")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["status"], CommunityEvent.CANCELLED)
        self.assertEqual(second.data["detail"], "This event is already cancelled.")
        self.assertEqual(
            Notification.objects.filter(recipient=self.member, notification_type=Notification.EVENT_CANCELLED).count(), 1
        )
        self.assertFalse(Notification.objects.filter(recipient=self.owner, notification_type=Notification.EVENT_CANCELLED).exists())

    def test_member_cannot_cancel_event(self):
        self.client.force_authenticate(self.member)

        response = self.client.post(f"/api/v1/events/{self.event.id}/cancel/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, CommunityEvent.SCHEDULED)

    def test_event_end_must_be_after_start(self):
        self.client.force_authenticate(self.owner)
        starts_at = timezone.now() + timedelta(days=3)

        response = self.client.post("/api/v1/events/", {
            "community": self.community.id,
            "title": "Backwards",
            "description": "Ends before it starts",
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at - timedelta(hours=1)).isoformat(),
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ends_at", response.data)

    def test_attendees_list_requires_membership(self):
        self.rsvp(self.member, EventRSVP.GOING)

        self.client.force_authenticate(self.outsider)
        denied = self.client.get(f"/api/v1/events/{self.event.id}/attendees/")
        self.client.force_authenticate(self.member)
        allowed = self.client.get(f"/api/v1/events/{self.event.id}/attendees/")

        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual([row["username"] for row in allowed.data], ["event_member"])


class SendEventRemindersCommandTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="reminder_owner", password="Strong-password-123")
        self.going = User.objects.create_user(username="reminder_going", password="Strong-password-123")
        self.interested = User.objects.create_user(username="reminder_interested", password="Strong-password-123")
        self.former = User.objects.create_user(username="reminder_former", password="Strong-password-123")
        self.community = make_community(self.owner)
        for user in (self.going, self.interested):
            CommunityMembership.objects.create(community=self.community, user=user)

    def run_command(self):
        out = StringIO()
        call_command("send_event_reminders", stdout=out)
        return out.getvalue()

    def reminders_for(self, user):
        return Notification.objects.filter(recipient=user, notification_type=Notification.EVENT_REMINDER)

    def test_one_hour_reminder_goes_only_to_active_members_who_are_going(self):
        event = make_event(self.community, self.owner, starts_in=timedelta(minutes=58))
        EventRSVP.objects.create(event=event, user=self.going, response=EventRSVP.GOING)
        EventRSVP.objects.create(event=event, user=self.interested, response=EventRSVP.INTERESTED)
        # RSVP'd "going" but no longer an active member of the community.
        EventRSVP.objects.create(event=event, user=self.former, response=EventRSVP.GOING)

        output = self.run_command()

        self.assertIn("Notifications sent: 1", output)
        reminder = self.reminders_for(self.going).get()
        self.assertEqual(reminder.data["reminder_type"], EventReminder.REMINDER_1_HOUR)
        self.assertIn("1 hour", reminder.body)
        self.assertFalse(self.reminders_for(self.interested).exists())
        self.assertFalse(self.reminders_for(self.former).exists())

    def test_twenty_four_hour_reminder_is_sent(self):
        event = make_event(self.community, self.owner, starts_in=timedelta(hours=23, minutes=58))
        EventRSVP.objects.create(event=event, user=self.going, response=EventRSVP.GOING)

        self.run_command()

        self.assertEqual(self.reminders_for(self.going).get().data["reminder_type"], EventReminder.REMINDER_24_HOURS)

    def test_reminders_are_not_sent_twice(self):
        event = make_event(self.community, self.owner, starts_in=timedelta(minutes=58))
        EventRSVP.objects.create(event=event, user=self.going, response=EventRSVP.GOING)

        self.run_command()
        second_output = self.run_command()

        self.assertIn("Processed: 0", second_output)
        self.assertEqual(self.reminders_for(self.going).count(), 1)
        self.assertEqual(EventReminder.objects.filter(event=event, user=self.going).count(), 1)

    def test_events_outside_window_or_cancelled_are_skipped(self):
        later = make_event(self.community, self.owner, starts_in=timedelta(hours=3), title="Later")
        cancelled = make_event(
            self.community, self.owner, starts_in=timedelta(minutes=58),
            title="Cancelled", status=CommunityEvent.CANCELLED,
        )
        for event in (later, cancelled):
            EventRSVP.objects.create(event=event, user=self.going, response=EventRSVP.GOING)

        output = self.run_command()

        self.assertIn("Processed: 0", output)
        self.assertFalse(self.reminders_for(self.going).exists())
