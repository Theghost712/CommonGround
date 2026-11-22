from django.contrib.auth import get_user_model
from django.contrib import admin
from rest_framework import status
from rest_framework.test import APITestCase
from django.test import TestCase

from apps.communities.models import Community, CommunityMembership
from .models import CommunityEvent, EventReminder, EventRSVP

User = get_user_model()


class CommunityEventAccessTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="event_owner", password="StrongPass123!")
        self.member = User.objects.create_user(username="event_member", password="StrongPass123!")
        self.outsider = User.objects.create_user(username="event_outsider", password="StrongPass123!")
        self.community = Community.objects.create(
            name="Event access", description="Event access policy",
            created_by=self.owner, visibility=Community.PUBLIC,
            approval_status=Community.APPROVED,
        )
        for user, role in [(self.owner, CommunityMembership.OWNER), (self.member, CommunityMembership.MEMBER)]:
            CommunityMembership.objects.create(
                community=self.community, user=user, role=role,
                status=CommunityMembership.ACTIVE,
            )
        self.event = CommunityEvent.objects.create(
            community=self.community,
            created_by=self.owner,
            title="Community event",
            description="Access policy test event",
            starts_at="2030-01-01T10:00:00Z",
            ends_at="2030-01-01T11:00:00Z",
        )

    def test_pending_rejected_and_suspended_events_are_hidden_from_creator(self):
        self.client.force_authenticate(self.owner)
        for approval_status in [Community.PENDING, Community.REJECTED, Community.SUSPENDED]:
            with self.subTest(approval_status=approval_status):
                self.community.approval_status = approval_status
                self.community.save(update_fields=["approval_status"])
                self.assertEqual(self.client.get(f"/api/v1/events/{self.event.id}/").status_code, status.HTTP_404_NOT_FOUND)

    def test_approved_community_event_visibility_rules(self):
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(f"/api/v1/events/{self.event.id}/").status_code, status.HTTP_200_OK)

        self.community.visibility = Community.RESTRICTED
        self.community.save(update_fields=["visibility"])
        self.assertEqual(self.client.get(f"/api/v1/events/{self.event.id}/").status_code, status.HTTP_200_OK)

        self.community.visibility = Community.PRIVATE
        self.community.save(update_fields=["visibility"])
        self.assertEqual(self.client.get(f"/api/v1/events/{self.event.id}/").status_code, status.HTTP_404_NOT_FOUND)
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(f"/api/v1/events/{self.event.id}/").status_code, status.HTTP_200_OK)

    def test_manager_cannot_create_event_in_unapproved_community(self):
        self.community.approval_status = Community.PENDING
        self.community.save(update_fields=["approval_status"])
        self.client.force_authenticate(self.owner)

        response = self.client.post(
            "/api/v1/events/",
            {
                "community": self.community.id,
                "title": "Premature event",
                "description": "Should be rejected",
                "starts_at": "2030-01-01T10:00:00Z",
                "ends_at": "2030-01-01T11:00:00Z",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_moderator_can_manage_events_but_member_cannot(self):
        moderator = User.objects.create_user(username="event_moderator", password="StrongPass123!")
        CommunityMembership.objects.create(
            community=self.community, user=moderator,
            role=CommunityMembership.MODERATOR,
            status=CommunityMembership.ACTIVE,
        )
        payload = {
            "community": self.community.id,
            "title": "Moderator event",
            "description": "Allowed for community moderators.",
            "starts_at": "2030-01-02T10:00:00Z",
            "ends_at": "2030-01-02T11:00:00Z",
        }

        self.client.force_authenticate(moderator)
        moderator_response = self.client.post("/api/v1/events/", payload, format="json")
        self.assertEqual(moderator_response.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(self.member)
        member_response = self.client.post(
            "/api/v1/events/",
            {**payload, "title": "Member event"},
            format="json",
        )
        self.assertEqual(member_response.status_code, status.HTTP_403_FORBIDDEN)


class EventAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username="event_admin", email="event-admin@example.test", password="StrongPass123!"
        )
        cls.community = Community.objects.create(
            name="Admin event community",
            description="Admin page test community",
            created_by=cls.admin_user,
            approval_status=Community.APPROVED,
        )
        cls.event = CommunityEvent.objects.create(
            community=cls.community,
            created_by=cls.admin_user,
            title="Admin event",
            description="Test event record",
            starts_at="2030-01-01T10:00:00Z",
            ends_at="2030-01-01T11:00:00Z",
        )
        cls.rsvp = EventRSVP.objects.create(
            event=cls.event, user=cls.admin_user, response=EventRSVP.GOING
        )
        cls.reminder = EventReminder.objects.create(
            event=cls.event,
            user=cls.admin_user,
            reminder_type=EventReminder.REMINDER_24_HOURS,
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_event_models_are_registered_and_admin_lists_render(self):
        for model, url in [
            (CommunityEvent, "/admin/events/communityevent/"),
            (EventRSVP, "/admin/events/eventrsvp/"),
            (EventReminder, "/admin/events/eventreminder/"),
        ]:
            with self.subTest(model=model.__name__):
                self.assertIn(model, admin.site._registry)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "CommonGround")

    def test_admins_use_search_filters_hierarchies_and_readonly_audit_fields(self):
        event_admin = admin.site._registry[CommunityEvent]
        rsvp_admin = admin.site._registry[EventRSVP]
        reminder_admin = admin.site._registry[EventReminder]

        self.assertIn("status", event_admin.list_filter)
        self.assertIn("community__name", event_admin.search_fields)
        self.assertEqual(event_admin.date_hierarchy, "starts_at")
        self.assertIn("created_by", event_admin.readonly_fields)
        self.assertIn("responded_at", rsvp_admin.readonly_fields)
        self.assertEqual(rsvp_admin.date_hierarchy, "responded_at")
        self.assertEqual(set(reminder_admin.readonly_fields), {"event", "user", "reminder_type", "sent_at"})
        self.assertEqual(reminder_admin.date_hierarchy, "sent_at")
        self.assertFalse(reminder_admin.has_add_permission(None))
