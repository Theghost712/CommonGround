from django.conf import settings
from django.db import models


class Call(models.Model):
    """A one-to-one WebRTC call. Media never touches the server; only signalling does."""

    AUDIO, VIDEO = "audio", "video"
    KINDS = [(AUDIO, "Voice"), (VIDEO, "Video")]
    RINGING, ACCEPTED, DECLINED, MISSED, CANCELLED, ENDED, FAILED = "ringing", "accepted", "declined", "missed", "cancelled", "ended", "failed"
    STATUSES = [(RINGING, "Ringing"), (ACCEPTED, "In progress"), (DECLINED, "Declined"), (MISSED, "Missed"),
                (CANCELLED, "Cancelled"), (ENDED, "Ended"), (FAILED, "Failed")]
    LIVE = (RINGING, ACCEPTED)

    conversation = models.ForeignKey("messaging.Conversation", on_delete=models.CASCADE, related_name="calls")
    caller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calls_made")
    callee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="calls_received")
    kind = models.CharField(max_length=5, choices=KINDS, default=AUDIO)
    status = models.CharField(max_length=10, choices=STATUSES, default=RINGING, db_index=True)
    # The callee's tab that answered; other tabs stop ringing and ignore signals.
    answered_device = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["caller", "status"]), models.Index(fields=["callee", "status"])]

    def __str__(self):
        return f"{self.get_kind_display()} call {self.caller} → {self.callee} ({self.status})"

    def other(self, user):
        return self.callee if user.pk == self.caller_id else self.caller

    def involves(self, user):
        return user.pk in (self.caller_id, self.callee_id)


class GroupCall(models.Model):
    """A call in a group chat. Media goes peer-to-peer in a full mesh (everyone
    connects to everyone), so it's capped at GROUP_CALL_MAX_PARTICIPANTS people."""

    LIVE, ENDED = "live", "ended"
    STATUSES = [(LIVE, "Live"), (ENDED, "Ended")]

    conversation = models.ForeignKey("messaging.Conversation", on_delete=models.CASCADE, related_name="group_calls")
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="group_calls_started")
    kind = models.CharField(max_length=5, choices=Call.KINDS, default=Call.AUDIO)
    status = models.CharField(max_length=5, choices=STATUSES, default=LIVE, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["conversation"], condition=models.Q(status="live"), name="one_live_group_call_per_chat")]

    def __str__(self):
        return f"{self.get_kind_display()} group call in chat {self.conversation_id} ({self.status})"


class GroupCallParticipant(models.Model):
    call = models.ForeignKey(GroupCall, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="group_call_participations")
    # The tab that joined; signals are only meant for it.
    device_id = models.CharField(max_length=64, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["joined_at", "id"]
        constraints = [models.UniqueConstraint(fields=["call", "user"], condition=models.Q(left_at__isnull=True), name="one_active_seat_per_user")]
        indexes = [models.Index(fields=["user", "left_at"])]

    def __str__(self):
        return f"{self.user} in group call {self.call_id}"
