from rest_framework import serializers

from .models import ConnectionLabel


class PersonSerializer(serializers.Serializer):
    """Public view of a member. Never includes email or phone number."""

    id = serializers.IntegerField()
    username = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    display_name = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()
    relationship = serializers.SerializerMethodField()
    reason = serializers.SerializerMethodField()

    def _profile(self, user):
        return getattr(user, "profile", None)

    def get_display_name(self, user):
        return user.get_full_name() or user.username

    def get_avatar_url(self, user):
        profile = self._profile(user)
        return profile.avatar_url if profile else ""

    def get_bio(self, user):
        profile = self._profile(user)
        return profile.bio if profile else ""

    def get_country(self, user):
        profile = self._profile(user)
        return profile.country if profile else ""

    def get_followers_count(self, user):
        total = getattr(user, "followers_total", None)
        return total if total is not None else user.follower_links.count()

    def get_following_count(self, user):
        total = getattr(user, "following_total", None)
        return total if total is not None else user.following_links.count()

    def get_relationship(self, user):
        return self.context.get("relations", {}).get(user.pk)

    def get_reason(self, user):
        return self.context.get("reasons", {}).get(user.pk)


class ProfileDetailSerializer(PersonSerializer):
    website = serializers.SerializerMethodField()
    interests = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField()
    discussions_count = serializers.SerializerMethodField()

    def get_website(self, user):
        profile = self._profile(user)
        return profile.website if profile else ""

    def get_interests(self, user):
        profile = self._profile(user)
        return [item.strip() for item in (profile.interests if profile else "").split(",") if item.strip()]

    def get_discussions_count(self, user):
        return self.context.get("discussions_count", 0)


class LabelSerializer(serializers.Serializer):
    label = serializers.ChoiceField(choices=ConnectionLabel.LABEL_CHOICES)


class PickedContactSerializer(serializers.Serializer):
    """One contact from the phone's contact picker: matched as a unit, so the app can
    show "Follow" for members and "Invite" for everyone else."""

    key = serializers.CharField(max_length=64)
    phones = serializers.ListField(child=serializers.CharField(max_length=40), required=False, default=list, max_length=10)
    emails = serializers.ListField(child=serializers.CharField(max_length=254), required=False, default=list, max_length=10)


class ContactMatchRequestSerializer(serializers.Serializer):
    MAX_ENTRIES = 2000

    phones = serializers.ListField(child=serializers.CharField(max_length=40), required=False, default=list)
    emails = serializers.ListField(child=serializers.CharField(max_length=254), required=False, default=list)
    contacts = PickedContactSerializer(many=True, required=False, default=list)

    def validate(self, attrs):
        for contact in attrs["contacts"]:
            attrs["phones"] = [*attrs["phones"], *contact["phones"]]
            attrs["emails"] = [*attrs["emails"], *contact["emails"]]
        total = len(attrs["phones"]) + len(attrs["emails"])
        if total == 0:
            raise serializers.ValidationError("Send at least one phone number or email address.")
        if total > self.MAX_ENTRIES:
            raise serializers.ValidationError(f"Send at most {self.MAX_ENTRIES} contacts at a time.")
        return attrs
