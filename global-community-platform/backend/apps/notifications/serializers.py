from rest_framework import serializers
from .models import Notification, NotificationPreference


class NotificationSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, allow_null=True)

    class Meta:
        model = Notification
        fields = [
            "id", "notification_type", "title", "body", "target_url", "data",
            "actor", "actor_username", "is_read", "read_at", "created_at",
        ]
        read_only_fields = fields


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            "messages_enabled", "discussions_enabled", "communities_enabled",
            "mentions_enabled", "system_enabled", "social_enabled",
            "sound_enabled", "popup_enabled", "updated_at",
        ]
        read_only_fields = ["updated_at"]
