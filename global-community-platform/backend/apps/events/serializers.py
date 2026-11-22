from django.db.models import Count, Q
from rest_framework import serializers

from apps.communities.models import Community
from .models import CommunityEvent, EventRSVP


class EventRSVPSerializer(serializers.ModelSerializer):
    username = serializers.CharField(
        source="user.username",
        read_only=True,
    )

    class Meta:
        model = EventRSVP
        fields = [
            "id",
            "event",
            "user",
            "username",
            "response",
            "responded_at",
        ]
        read_only_fields = [
            "id",
            "event",
            "user",
            "username",
            "responded_at",
        ]


class CommunityEventSerializer(serializers.ModelSerializer):
    community = serializers.PrimaryKeyRelatedField(
        queryset=Community.objects.all()
    )

    community_name = serializers.CharField(
        source="community.name",
        read_only=True,
    )

    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
    )

    rsvp_counts = serializers.SerializerMethodField()
    my_response = serializers.SerializerMethodField()

    class Meta:
        model = CommunityEvent
        fields = [
            "id",
            "community",
            "community_name",
            "created_by",
            "created_by_username",
            "title",
            "description",
            "location",
            "starts_at",
            "ends_at",
            "status",
            "rsvp_counts",
            "my_response",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "created_by",
            "created_by_username",
            "community_name",
            "rsvp_counts",
            "my_response",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        starts_at = attrs.get(
            "starts_at",
            getattr(self.instance, "starts_at", None),
        )

        ends_at = attrs.get(
            "ends_at",
            getattr(self.instance, "ends_at", None),
        )

        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError({
                "ends_at": "Event end time must be after start time."
            })

        return attrs

    def get_rsvp_counts(self, obj):
        counts = obj.rsvps.aggregate(
            going=Count(
                "id",
                filter=Q(response=EventRSVP.GOING),
            ),
            interested=Count(
                "id",
                filter=Q(response=EventRSVP.INTERESTED),
            ),
            not_going=Count(
                "id",
                filter=Q(response=EventRSVP.NOT_GOING),
            ),
        )

        return counts

    def get_my_response(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return None

        return obj.rsvps.filter(
            user=request.user
        ).values_list("response", flat=True).first()
