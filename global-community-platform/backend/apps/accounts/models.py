from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    LANGUAGE_CHOICES = [
        ("en", "English"),
        ("sw", "Kiswahili"),
        ("fr", "Français"),
        ("es", "Español"),
        ("ar", "العربية"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    bio = models.CharField(max_length=300, blank=True)
    country = models.CharField(max_length=100, blank=True)
    preferred_language = models.CharField(
        max_length=5, choices=LANGUAGE_CHOICES, default="en"
    )
    interests = models.CharField(
        max_length=500,
        blank=True,
        help_text="Comma-separated interests, for example: technology, education, business.",
    )
    avatar_url = models.URLField(max_length=500, blank=True)
    website = models.URLField(max_length=500, blank=True)
    # Private: never returned to other users. Stored normalised (international digits).
    phone_number = models.CharField(max_length=20, blank=True)
    phone_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    # Opt-in: lets people who have this phone number or email in their contacts find this account.
    discoverable_by_contacts = models.BooleanField(default=False)
    # Private account: only approved followers see posts, stories and follower lists.
    is_private = models.BooleanField(default=False)
    # Set when the user proves they own user.email. Cleared when the email changes.
    email_verified_at = models.DateTimeField(null=True, blank=True)
    # Access and refresh tokens issued before this moment are rejected
    # ("sign out everywhere", password change and password reset).
    sessions_revoked_at = models.DateTimeField(null=True, blank=True)
    # Moderation: can't sign in until this time (bans use user.is_active=False instead).
    suspended_until = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Profile: {self.user.username}"

    def save(self, *args, **kwargs):
        from .phone import phone_hash

        self.phone_hash = phone_hash(self.phone_number)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "phone_number" in update_fields:
            kwargs["update_fields"] = {*update_fields, "phone_hash"}
        super().save(*args, **kwargs)


class TwoFactorAuth(models.Model):
    """Authenticator-app (TOTP, RFC 6238) second factor for one account.

    The shared secret is encrypted at rest (see two_factor.encrypt_secret).
    The row exists from setup; two-factor is on only once confirmed_at is set.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="two_factor")
    secret_encrypted = models.TextField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # The last 30-second time step accepted, so a code can't be used twice.
    last_used_step = models.BigIntegerField(default=0)
    # Keyed hashes of the one-use recovery codes that are still unused.
    recovery_code_hashes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"2FA for {self.user.username} ({'on' if self.enabled else 'pending'})"

    @property
    def enabled(self):
        return self.confirmed_at is not None
