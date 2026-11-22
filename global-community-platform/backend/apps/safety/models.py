from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Block(models.Model):
    """`blocker` and `blocked` disappear from each other entirely. Silent: no notification."""

    blocker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocks_made")
    blocked = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="blocks_received")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["blocker", "blocked"], name="unique_block"),
            models.CheckConstraint(condition=~Q(blocker=F("blocked")), name="no_self_block"),
        ]
        indexes = [models.Index(fields=["blocked", "blocker"])]


class Mute(models.Model):
    """Hide someone's posts and stories from your feed without unfollowing them."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mutes")
    muted = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    mute_posts = models.BooleanField(default=True)
    mute_stories = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "muted"], name="unique_mute")]


class Report(models.Model):
    USER, POST, COMMENT, STORY, MESSAGE = "user", "post", "comment", "story", "message"
    TARGETS = [(USER, "Account"), (POST, "Post"), (COMMENT, "Comment"), (STORY, "Story"), (MESSAGE, "Message")]
    REASONS = [
        ("spam", "Spam"),
        ("harassment", "Bullying or harassment"),
        ("hate", "Hate speech or symbols"),
        ("violence", "Violence or threats"),
        ("nudity", "Nudity or sexual content"),
        ("self_harm", "Suicide or self-harm"),
        ("scam", "Scam or fraud"),
        ("false_info", "False information"),
        ("impersonation", "Pretending to be someone else"),
        ("ip", "Intellectual property"),
        ("other", "Something else"),
    ]
    OPEN, ACTIONED, DISMISSED = "open", "actioned", "dismissed"
    STATUSES = [(OPEN, "Open"), (ACTIONED, "Action taken"), (DISMISSED, "No violation")]

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports_made")
    target_type = models.CharField(max_length=8, choices=TARGETS)
    target_id = models.PositiveBigIntegerField()
    target_owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reports_received")
    reason = models.CharField(max_length=16, choices=REASONS)
    details = models.TextField(max_length=1000, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default=OPEN, db_index=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["reporter", "target_type", "target_id"], name="one_report_per_target")]
        indexes = [models.Index(fields=["target_type", "target_id"])]
