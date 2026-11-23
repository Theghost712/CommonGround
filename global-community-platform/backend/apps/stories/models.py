from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

STORY_LIFETIME = timedelta(hours=24)


def default_expiry():
    return timezone.now() + STORY_LIFETIME


class Story(models.Model):
    IMAGE, VIDEO, TEXT = "image", "video", "text"
    MEDIA_TYPES = [(IMAGE, "Photo"), (VIDEO, "Video"), (TEXT, "Text")]
    FOLLOWERS, CLOSE_FRIENDS = "followers", "close_friends"
    AUDIENCES = [(FOLLOWERS, "Followers"), (CLOSE_FRIENDS, "Close friends")]
    BACKGROUNDS = ["violet", "sunset", "ocean", "forest", "night", "rose"]

    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="stories")
    media_type = models.CharField(max_length=5, choices=MEDIA_TYPES)
    media = models.FileField(upload_to="stories/%Y/%m/%d/", blank=True)
    thumbnail = models.FileField(upload_to="stories/thumbs/%Y/%m/%d/", blank=True)
    text = models.CharField(max_length=500, blank=True)
    background = models.CharField(max_length=12, default="violet")
    alt_text = models.CharField(max_length=300, blank=True)
    duration_ms = models.PositiveIntegerField(default=5000)
    # Server-side video conversion (apps/common/video.py).
    processing = models.CharField(max_length=8, blank=True, default="", db_index=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_attempts = models.PositiveSmallIntegerField(default=0)
    audience = models.CharField(max_length=13, choices=AUDIENCES, default=FOLLOWERS)
    view_count = models.PositiveIntegerField(default=0)  # denormalised so the author's view counter never needs COUNT(*)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_expiry, db_index=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["author", "expires_at"])]
        verbose_name_plural = "stories"

    @property
    def is_active(self):
        return self.expires_at > timezone.now()

    def delete_files(self):
        for field in (self.media, self.thumbnail):
            if field:
                field.delete(save=False)


class StoryView(models.Model):
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="views")
    viewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="story_views")
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-viewed_at"]
        constraints = [models.UniqueConstraint(fields=["story", "viewer"], name="unique_story_view")]
        indexes = [models.Index(fields=["viewer", "story"])]


class CloseFriend(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="close_friends")
    friend = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "friend"], name="unique_close_friend")]


class StoryHiddenFrom(models.Model):
    """People who never see the owner's stories, even if they follow them."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="story_hidden_from")
    hidden_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "hidden_user"], name="unique_story_hidden")]


class StoryHighlight(models.Model):
    """A named collection of the owner's stories kept on their profile after 24 hours."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="story_highlights")
    title = models.CharField(max_length=40)
    stories = models.ManyToManyField(Story, through="StoryHighlightItem", related_name="highlights")
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "-created_at"]

    def __str__(self):
        return f"{self.owner}: {self.title}"


class StoryHighlightItem(models.Model):
    highlight = models.ForeignKey(StoryHighlight, on_delete=models.CASCADE, related_name="items")
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name="highlight_items")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["added_at", "id"]
        constraints = [models.UniqueConstraint(fields=["highlight", "story"], name="story_once_per_highlight")]
