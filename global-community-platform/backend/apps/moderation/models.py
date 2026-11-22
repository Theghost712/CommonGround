from django.conf import settings
from django.db import models


class ModerationAction(models.Model):
    """Audit log: every moderation decision, with a snapshot of removed content."""

    DISMISS, REMOVE, WARN, SUSPEND, BAN, RESTORE = "dismiss", "remove", "warn", "suspend", "ban", "restore"
    ACTIONS = [
        (DISMISS, "Dismissed reports"),
        (REMOVE, "Removed content"),
        (WARN, "Warned user"),
        (SUSPEND, "Suspended user"),
        (BAN, "Banned user"),
        (RESTORE, "Lifted suspension or ban"),
    ]

    moderator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="moderation_actions")
    action = models.CharField(max_length=10, choices=ACTIONS)
    target_type = models.CharField(max_length=8, blank=True)
    target_id = models.PositiveBigIntegerField(null=True, blank=True)
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="moderation_history")
    community = models.ForeignKey("communities.Community", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reason = models.TextField(max_length=1000, blank=True)
    # What the content said when it was removed (evidence for appeals and audits).
    snapshot = models.JSONField(default=dict, blank=True)
    reports_closed = models.PositiveIntegerField(default=0)
    suspended_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["target_user", "-created_at"])]

    def __str__(self):
        return f"{self.get_action_display()} by {self.moderator} ({self.created_at:%Y-%m-%d})"
