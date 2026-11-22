from pathlib import Path

from django.conf import settings
from django.db import models


class Hashtag(models.Model):
    name = models.CharField(max_length=60, unique=True)  # stored lowercase, without '#'
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"#{self.name}"


class Discussion(models.Model):
    community = models.ForeignKey("communities.Community", on_delete=models.CASCADE, related_name="discussions", null=True, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="discussions")
    # Photo posts (like Instagram) may have neither a title nor a caption.
    title = models.CharField(max_length=180, blank=True)
    body = models.TextField(max_length=10000, blank=True)
    content_html = models.TextField(blank=True, default="")
    category = models.CharField(max_length=60, default="General", db_index=True)
    hashtags = models.ManyToManyField(Hashtag, blank=True, related_name="discussions")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["category"]),
            # Profile grids and the Following feed: posts by an author, newest first.
            models.Index(fields=["author", "-created_at"], name="discussion_author_recent"),
            # Community feeds.
            models.Index(fields=["community", "-created_at"], name="discussion_community_recent"),
        ]

    def __str__(self):
        return self.title or self.body[:60] or f"Post {self.pk}"


class Comment(models.Model):
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="discussion_comments")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies")
    body = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["discussion", "created_at"])]

    def __str__(self):
        return f"Comment by {self.author}"


class DiscussionReaction(models.Model):
    REACTION_CHOICES = [("like", "Like"), ("insightful", "Insightful"), ("support", "Support"), ("celebrate", "Celebrate")]
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="discussion_reactions")
    reaction_type = models.CharField(max_length=20, choices=REACTION_CHOICES, default="like")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["discussion", "user"], name="unique_discussion_reaction")]
        indexes = [models.Index(fields=["discussion", "reaction_type"])]

    def __str__(self):
        return f"{self.user} reacted {self.reaction_type} to {self.discussion}"


class DiscussionBookmark(models.Model):
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name="bookmarks")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="discussion_bookmarks")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["discussion", "user"], name="unique_discussion_bookmark")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} saved {self.discussion}"


class DiscussionAttachment(models.Model):
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="discussion_attachments")
    file = models.FileField(upload_to="discussion_attachments/%Y/%m/")
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    # Optimised copies for photos (WebP, metadata stripped) and layout hints.
    display = models.FileField(upload_to="discussion_images/%Y/%m/", blank=True)
    thumbnail = models.FileField(upload_to="discussion_images/thumbs/%Y/%m/", blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    color = models.CharField(max_length=7, blank=True)
    alt_text = models.CharField(max_length=300, blank=True)
    # Video posts: `file` is the video, `display`/`thumbnail` hold the poster frame.
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    @property
    def is_image(self):
        return self.content_type.startswith("image/")

    def __str__(self):
        return self.original_name or Path(self.file.name).name


class Poll(models.Model):
    """A poll attached to a post. Options can't change once people have voted."""

    discussion = models.OneToOneField(Discussion, on_delete=models.CASCADE, related_name="poll")
    question = models.CharField(max_length=300)
    allows_multiple = models.BooleanField(default=False)
    closes_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question

    @property
    def is_closed(self):
        from django.utils import timezone

        return self.closes_at is not None and self.closes_at <= timezone.now()


class PollOption(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="options")
    text = models.CharField(max_length=100)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.text


class PollVote(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="votes")
    option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name="votes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="poll_votes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["option", "user"], name="one_vote_per_option")]
        indexes = [models.Index(fields=["poll", "user"], name="pollvote_poll_user")]
