from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    MESSAGE = "message"
    DISCUSSION_COMMENT = "discussion_comment"
    DISCUSSION_REPLY = "discussion_reply"
    DISCUSSION_REACTION = "discussion_reaction"
    MENTION = "mention"

    COMMUNITY_MEMBERSHIP_REQUEST = "membership_request"
    COMMUNITY_MEMBERSHIP_APPROVED = "membership_approved"
    COMMUNITY_ANNOUNCEMENT = "community_announcement"
    COMMUNITY_INVITATION = "community_invitation"

    EVENT_CREATED = "event_created"
    EVENT_UPDATED = "event_updated"
    EVENT_CANCELLED = "event_cancelled"
    EVENT_RSVP = "event_rsvp"
    EVENT_REMINDER = "event_reminder"

    FOLLOW = "follow"
    FOLLOW_REQUEST = "follow_request"
    FOLLOW_ACCEPTED = "follow_accepted"

    SYSTEM = "system"

    TYPE_CHOICES = [
        (MESSAGE, "New message"),
        (DISCUSSION_COMMENT, "Discussion comment"),
        (DISCUSSION_REPLY, "Comment reply"),
        (DISCUSSION_REACTION, "Discussion reaction"),
        (MENTION, "Mention"),
        (COMMUNITY_MEMBERSHIP_REQUEST, "Community membership request"),
        (COMMUNITY_MEMBERSHIP_APPROVED, "Community membership approved"),
        (COMMUNITY_ANNOUNCEMENT, "Community announcement"),
        (COMMUNITY_INVITATION, "Community invitation"),
        (EVENT_CREATED, "New community event"),
        (EVENT_UPDATED, "Community event updated"),
        (EVENT_CANCELLED, "Community event cancelled"),
        (EVENT_RSVP, "Event RSVP"),
        (EVENT_REMINDER, "Event reminder"),
        (FOLLOW, "New follower"),
        (FOLLOW_REQUEST, "Follow request"),
        (FOLLOW_ACCEPTED, "Follow request accepted"),
        (SYSTEM, "System notification"),
    ]
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_notifications",
    )
    notification_type = models.CharField(max_length=32, choices=TYPE_CHOICES, default=SYSTEM)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=500, blank=True)
    target_url = models.CharField(max_length=500, blank=True)
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["recipient", "is_read", "-created_at"]),
            models.Index(fields=["recipient", "-created_at"]),
        ]

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])

    def __str__(self):
        return f"{self.recipient}: {self.title}"


class NotificationPreference(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    messages_enabled = models.BooleanField(default=True)
    discussions_enabled = models.BooleanField(default=True)
    communities_enabled = models.BooleanField(default=True)
    mentions_enabled = models.BooleanField(default=True)
    system_enabled = models.BooleanField(default=True)
    social_enabled = models.BooleanField(default=True)
    # Delivery on this account's devices: a short chime, and a system pop-up when the tab is hidden.
    sound_enabled = models.BooleanField(default=True)
    popup_enabled = models.BooleanField(default=True)
    # Weekly "what you missed" email (apps/notifications/digest.py).
    email_digest_enabled = models.BooleanField(default=True)
    digest_sent_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notification preferences: {self.user.username}"


class PushSubscription(models.Model):
    """One browser/device that asked for push notifications (Web Push, RFC 8030).

    The endpoint is a capability URL from the browser's push service; keys encrypt
    the payload so only that browser can read it.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.URLField(max_length=1000, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    failure_count = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"Push for {self.user_id}: {self.endpoint[:60]}"
