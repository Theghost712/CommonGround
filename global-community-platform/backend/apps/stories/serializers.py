from rest_framework import serializers

from apps.social.serializers import PersonSerializer

from .access import media_url
from .models import Story

MAX_VIDEO_MS = 60_000


class StorySerializer(serializers.ModelSerializer):
    media_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    seen = serializers.SerializerMethodField()
    view_count = serializers.SerializerMethodField()
    is_own = serializers.SerializerMethodField()

    class Meta:
        model = Story
        fields = [
            "id", "media_type", "media_url", "thumbnail_url", "text", "background", "alt_text",
            "duration_ms", "audience", "created_at", "expires_at", "seen", "view_count", "is_own",
        ]

    def _viewer(self):
        return self.context["request"].user

    def get_media_url(self, story):
        return media_url(self.context["request"], story, self._viewer(), "media")

    def get_thumbnail_url(self, story):
        return media_url(self.context["request"], story, self._viewer(), "thumb")

    def get_seen(self, story):
        return story.pk in self.context.get("seen_ids", set()) or story.author_id == self._viewer().pk

    def get_view_count(self, story):
        # Only the author learns how many people watched.
        return story.view_count if story.author_id == self._viewer().pk else None

    def get_is_own(self, story):
        return story.author_id == self._viewer().pk


class StoryCreateSerializer(serializers.Serializer):
    media_type = serializers.ChoiceField(choices=Story.MEDIA_TYPES)
    file = serializers.FileField(required=False)
    # Alternative to `file`: a key from /uploads/ (uploaded straight to storage).
    file_key = serializers.CharField(required=False, allow_blank=True, max_length=300)
    thumbnail = serializers.FileField(required=False)
    text = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    background = serializers.ChoiceField(choices=[(b, b) for b in Story.BACKGROUNDS], required=False, default="violet")
    alt_text = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    duration_ms = serializers.IntegerField(required=False, min_value=1000, max_value=MAX_VIDEO_MS, default=5000)
    audience = serializers.ChoiceField(choices=Story.AUDIENCES, required=False, default=Story.FOLLOWERS)

    def validate(self, attrs):
        kind = attrs["media_type"]
        if kind in (Story.IMAGE, Story.VIDEO) and not attrs.get("file") and not attrs.get("file_key"):
            raise serializers.ValidationError({"file": "Choose a photo or video."})
        if kind == Story.TEXT and not attrs.get("text", "").strip():
            raise serializers.ValidationError({"text": "Write something for your story."})
        return attrs


class TrayEntrySerializer(serializers.Serializer):
    user = PersonSerializer()
    stories = StorySerializer(many=True)
    all_seen = serializers.BooleanField()
    latest_at = serializers.DateTimeField()
