from django.conf import settings
from django.db import models


class Conversation(models.Model):
    DIRECT = "direct"
    GROUP = "group"
    TYPE_CHOICES = [(DIRECT, "Direct"), (GROUP, "Group")]

    conversation_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=DIRECT, db_index=True)
    title = models.CharField(max_length=120, blank=True)
    # Disappearing messages: new messages are deleted this many seconds after sending (0 = off).
    disappear_seconds = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_conversations")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title or f"{self.conversation_type.title()} conversation #{self.pk}"


class ConversationMember(models.Model):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    ROLE_CHOICES = [(OWNER, "Owner"), (ADMIN, "Administrator"), (MEMBER, "Member")]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_memberships")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "user"], name="unique_conversation_member")]
        indexes = [models.Index(fields=["user", "is_active", "conversation"])]
        ordering = ["joined_at"]

    def __str__(self):
        return f"{self.user} in {self.conversation}"


class Message(models.Model):
    TEXT, PHOTO, VIDEO, VOICE, POST, SYSTEM = "text", "photo", "video", "voice", "post", "system"
    KINDS = [(TEXT, "Text"), (PHOTO, "Photo"), (VIDEO, "Video"), (VOICE, "Voice message"), (POST, "Shared post"), (SYSTEM, "Notice")]
    MEDIA_KINDS = (PHOTO, VIDEO, VOICE)

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_chat_messages")
    kind = models.CharField(max_length=6, choices=KINDS, default=TEXT)
    body = models.TextField(max_length=4000, blank=True)
    # Photos are re-encoded WebP, videos H.264 MP4 (apps/common/video.py), voice AAC M4A.
    media = models.FileField(upload_to="chat/%Y/%m/", blank=True)
    thumbnail = models.FileField(upload_to="chat/thumbs/%Y/%m/", blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    processing = models.CharField(max_length=8, blank=True, default="", db_index=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_attempts = models.PositiveSmallIntegerField(default=0)
    # View once: each recipient can open the photo/video a single time; then it's deleted.
    view_once = models.BooleanField(default=False)
    shared_post = models.ForeignKey("discussions.Discussion", null=True, blank=True, on_delete=models.SET_NULL, related_name="shares_in_chat")
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    def delete_files(self):
        for field in (self.media, self.thumbnail):
            if field:
                try:
                    field.delete(save=False)
                except Exception:
                    pass

    @property
    def preview(self):
        """One line for chat lists and notifications."""
        if self.deleted_at:
            return "Message deleted"
        labels = {self.PHOTO: "📷 Photo", self.VIDEO: "🎥 Video", self.VOICE: "🎤 Voice message", self.POST: "↗ Shared a post"}
        if self.kind in labels:
            label = ("👁 View-once " + labels[self.kind].split(" ", 1)[1].lower()) if self.view_once else labels[self.kind]
            return f"{label}: {self.body}" if self.body and not self.view_once else label
        return self.body

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self):
        return f"Message #{self.pk} from {self.sender}"


class MessageOpen(models.Model):
    """A recipient opened a view-once photo or video."""

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="opens")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="opened_messages")
    opened_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["message", "user"], name="one_open_per_user")]


class MessageReadReceipt(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="read_receipts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_read_receipts")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["message", "user"], name="unique_message_read_receipt")]
        indexes = [models.Index(fields=["user", "read_at"])]

    def __str__(self):
        return f"{self.user} read message #{self.message_id}"

class UserPresence(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="presence",
    )

    is_online = models.BooleanField(default=False, db_index=True)

    last_seen = models.DateTimeField(
        null=True,
        blank=True,
    )

    active_connections = models.PositiveIntegerField(default=0)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "User presences"

    def __str__(self):
        status = "Online" if self.is_online else "Offline"
        return f"{self.user.username} - {status}"
