from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Follow(models.Model):
    follower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="following_links")
    following = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="follower_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["follower", "following"], name="unique_follow"),
            models.CheckConstraint(condition=~Q(follower=F("following")), name="no_self_follow"),
        ]
        indexes = [models.Index(fields=["following", "follower"])]

    def __str__(self):
        return f"{self.follower} → {self.following}"


class ConnectionLabel(models.Model):
    """A private tag one member puts on another (only the owner ever sees it)."""

    FAMILY = "family"
    FRIEND = "friend"
    COLLEAGUE = "colleague"
    CLASSMATE = "classmate"
    NEIGHBOUR = "neighbour"
    OTHER = "other"
    LABEL_CHOICES = [
        (FAMILY, "Family"),
        (FRIEND, "Friend"),
        (COLLEAGUE, "Colleague"),
        (CLASSMATE, "Classmate"),
        (NEIGHBOUR, "Neighbour"),
        (OTHER, "Other"),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="connection_labels")
    target = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    label = models.CharField(max_length=12, choices=LABEL_CHOICES)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "target"], name="unique_connection_label")]


class ContactMatch(models.Model):
    """Records that `target` was found in `owner`'s phone book. Raw contacts are never stored."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="contact_matches")
    target = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    matched_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "target"], name="unique_contact_match")]


class FollowRequest(models.Model):
    """A pending request to follow a private account."""

    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="follow_requests_sent")
    target = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="follow_requests_received")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["requester", "target"], name="unique_follow_request")]
