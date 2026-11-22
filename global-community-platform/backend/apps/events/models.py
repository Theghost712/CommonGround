from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.communities.models import Community


class CommunityEvent(models.Model):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (SCHEDULED, "Scheduled"),
        (CANCELLED, "Cancelled"),
    ]

    community = models.ForeignKey(
        Community,
        on_delete=models.CASCADE,
        related_name="events",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_community_events",
    )

    title = models.CharField(max_length=160)
    description = models.TextField(max_length=5000)
    location = models.CharField(max_length=255, blank=True)

    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()

    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=SCHEDULED,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["community", "starts_at"]),
            models.Index(fields=["status", "starts_at"]),
        ]

    def clean(self):
        if self.starts_at and self.ends_at:
            if self.ends_at <= self.starts_at:
                raise ValidationError({
                    "ends_at": "Event end time must be after start time."
                })

    def __str__(self):
        return f"{self.title} - {self.community.name}"


class EventRSVP(models.Model):
    GOING = "going"
    INTERESTED = "interested"
    NOT_GOING = "not_going"

    RESPONSE_CHOICES = [
        (GOING, "Going"),
        (INTERESTED, "Interested"),
        (NOT_GOING, "Not Going"),
    ]

    event = models.ForeignKey(
        CommunityEvent,
        on_delete=models.CASCADE,
        related_name="rsvps",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_rsvps",
    )

    response = models.CharField(
        max_length=12,
        choices=RESPONSE_CHOICES,
    )

    responded_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"],
                name="unique_event_user_rsvp",
            ),
        ]

        indexes = [
            models.Index(fields=["event", "response"]),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.event.title} ({self.response})"

class EventReminder(models.Model):
    REMINDER_24_HOURS = "24h"
    REMINDER_1_HOUR = "1h"

    REMINDER_CHOICES = [
        (REMINDER_24_HOURS, "24 hours before"),
        (REMINDER_1_HOUR, "1 hour before"),
    ]

    event = models.ForeignKey(
        CommunityEvent,
        on_delete=models.CASCADE,
        related_name="reminders",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_reminders",
    )

    reminder_type = models.CharField(
        max_length=8,
        choices=REMINDER_CHOICES,
    )

    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user", "reminder_type"],
                name="unique_event_user_reminder",
            ),
        ]

        indexes = [
            models.Index(fields=["user", "sent_at"]),
        ]

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{self.event.title} - {self.reminder_type}"
        )
