from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import UserProfile

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    email_verified = serializers.SerializerMethodField()
    can_moderate = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "email_verified", "can_moderate", "is_staff", "first_name", "last_name", "date_joined"]
        # Email changes go through /auth/email/change/ (password + confirmation link).
        read_only_fields = ["id", "email", "is_staff", "date_joined"]

    def get_can_moderate(self, user):
        from apps.moderation.services import can_moderate

        return can_moderate(user)

    def get_email_verified(self, user):
        profile = getattr(user, "profile", None)
        return bool(profile and profile.email_verified_at)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    # Username of the member whose invite link brought this person here (optional).
    invited_by = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=150)

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "password", "password_confirm", "invited_by",
        ]
        read_only_fields = ["id"]

    RESERVED_USERNAMES = {"suggestions", "contacts", "stories", "requests", "discover", "invite", "me", "admin", "api"}

    def validate_username(self, value):
        if value.lower() in self.RESERVED_USERNAMES:
            raise serializers.ValidationError("This username is reserved. Please choose another.")
        return value

    def validate_email(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Enter your email address. You'll need it to reset your password.")
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists. Try signing in or resetting your password.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        invited_by = validated_data.pop("invited_by", "").strip().lstrip("@")
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        UserProfile.objects.get_or_create(user=user)
        from .security import send_verification_email

        send_verification_email(user)
        if invited_by:
            from apps.social.invites import welcome_invited_user

            welcome_invited_user(user, invited_by)
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", required=False, allow_blank=True)
    last_name = serializers.CharField(source="user.last_name", required=False, allow_blank=True)
    date_joined = serializers.DateTimeField(source="user.date_joined", read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            "id", "username", "email", "first_name", "last_name", "date_joined",
            "bio", "country", "preferred_language", "interests", "avatar_url",
            "website", "phone_number", "discoverable_by_contacts", "is_private", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "username", "email", "date_joined", "created_at", "updated_at"]

    def validate_phone_number(self, value):
        if not value or not value.strip():
            return ""
        from .phone import normalize_phone

        normalized = normalize_phone(value)
        if not normalized:
            raise serializers.ValidationError("Enter a valid phone number, e.g. +255 712 345 678.")
        others = UserProfile.objects.filter(phone_number=normalized)
        if self.instance is not None:
            others = others.exclude(pk=self.instance.pk)
        if others.exists():
            raise serializers.ValidationError("This phone number is already linked to another account.")
        return normalized

    def update(self, instance, validated_data):
        going_public = instance.is_private and validated_data.get("is_private") is False
        user_data = validated_data.pop("user", {})
        if user_data:
            user = instance.user
            for field, value in user_data.items():
                setattr(user, field, value)
            user.save(update_fields=list(user_data.keys()))
        profile = super().update(instance, validated_data)
        if going_public:
            # Like Instagram: switching to public approves everyone who was waiting.
            from apps.social.services import approve_all_requests

            approve_all_requests(profile.user)
        return profile
