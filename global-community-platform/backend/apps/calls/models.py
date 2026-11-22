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
