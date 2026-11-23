from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.communities.models import CommunityMembership
from apps.events.models import CommunityEvent, EventRSVP, EventReminder
from apps.notifications.models import Notification
from apps.notifications.services import create_notification


def starts_in_words(delta):
    minutes = max(1, round(delta.total_seconds() / 60))
    if minutes >= 23 * 60:
        return "in about 24 hours"
    if minutes >= 110:
        return f"in about {round(minutes / 60)} hours"
    if minutes >= 50:
        return "in about 1 hour"
    return f"in {minutes} minutes"


class Command(BaseCommand):
    help = "Send automatic reminders for upcoming community events."

    def handle(self, *args, **options):
        now = timezone.now()
        # Each reminder looks back over a catch-up window, so a delayed or missed
        # run (a sleeping server, a skipped cron) still sends it. EventReminder rows
        # make sure nobody gets the same reminder twice.
        reminder_types = [
            (EventReminder.REMINDER_24_HOURS, timedelta(hours=24), timedelta(hours=4)),
            (EventReminder.REMINDER_1_HOUR, timedelta(hours=1), timedelta(minutes=50)),
        ]

        sent_count = 0
        processed_count = 0

        for reminder_type, lead_time, catch_up in reminder_types:

            window_start = now + lead_time - catch_up
            window_end = now + lead_time

            events = CommunityEvent.objects.filter(
                status=CommunityEvent.SCHEDULED,
                starts_at__gt=window_start,
                starts_at__lte=window_end,
            ).select_related("community")

            for event in events:

                going_members = EventRSVP.objects.filter(
                    event=event,
                    response=EventRSVP.GOING,
                    user__is_active=True,
                    user__community_memberships__community_id=event.community_id,
                    user__community_memberships__status=CommunityMembership.ACTIVE,
                ).select_related("user").distinct()

                for rsvp in going_members:

                    with transaction.atomic():
                        reminder, created = EventReminder.objects.get_or_create(
                            event=event,
                            user=rsvp.user,
                            reminder_type=reminder_type,
                        )

                        if not created:
                            continue

                        notification = create_notification(
                            recipient=rsvp.user,
                            notification_type=Notification.EVENT_REMINDER,
                            title=f"Reminder: {event.title}",
                            body=f"Your event starts {starts_in_words(event.starts_at - now)}.",
                            target_url=(
                                f"/communities/{event.community_id}?tab=events"
                            ),
                            actor=None,
                            data={
                                "event_id": event.id,
                                "community_id": event.community_id,
                                "reminder_type": reminder_type,
                                "starts_at": event.starts_at.isoformat(),
                            },
                        )

                        processed_count += 1

                        if notification:
                            sent_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Reminder processing completed. "
                f"Processed: {processed_count}, "
                f"Notifications sent: {sent_count}."
            )
        )
