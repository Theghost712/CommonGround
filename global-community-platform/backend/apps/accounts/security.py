"""Account security: signed email links, session revocation and security emails.

Tokens in links are never stored. Password-reset tokens come from Django's
default_token_generator, which hashes the current password, so a link stops
working once it has been used. Email links are signed with SECRET_KEY and bind the
user id and the address, so they stop working when the email changes.
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from .models import UserProfile

logger = logging.getLogger(__name__)
User = get_user_model()

EMAIL_SALT = "accounts.email-link"
REVOKED_CACHE_KEY = "auth:revoked-at:{}"


# ---------------------------------------------------------------- links

def frontend_link(path, **params):
    from urllib.parse import urlencode

    return f"{settings.FRONTEND_URL.rstrip('/')}{path}?{urlencode(params)}"


def make_email_token(user, purpose="verify", new_email=None):
    payload = {"u": user.pk, "p": purpose, "e": user.email.lower()}
    if new_email:
        payload["n"] = new_email
    return signing.dumps(payload, salt=EMAIL_SALT, compress=True)


def read_email_token(token):
    """Return (user, payload) for a valid, unexpired, still-current email link, else (None, None)."""
    try:
        payload = signing.loads(token, salt=EMAIL_SALT, max_age=settings.EMAIL_LINK_MAX_AGE_SECONDS)
    except (signing.BadSignature, TypeError):
        return None, None
    user = User.objects.filter(pk=payload.get("u"), is_active=True).first()
    # The link names the address it was sent for; once the account's email
    # changes, older links are dead.
    if user is None or user.email.lower() != payload.get("e"):
        return None, None
    return user, payload


def make_reset_link(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    return frontend_link("/reset-password", uid=uid, token=default_token_generator.make_token(user))


def user_from_reset(uid, token):
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return None
    return user if default_token_generator.check_token(user, token) else None


# ---------------------------------------------------------------- email

def _send(to, subject, body):
    """Send a plain-text security email. Failures are logged, never shown to the client."""
    try:
        send_mail(f"CommonGround: {subject}", body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
        return True
    except Exception:  # SMTP outages must not break registration or reveal anything.
        logger.exception("Could not send %r email", subject)
        return False


def send_verification_email(user):
    if not user.email:
        return False
    link = frontend_link("/verify-email", token=make_email_token(user))
    return _send(user.email, "confirm your email address", (
        f"Hi {user.first_name or user.username},\n\n"
        f"Please confirm that this is your email address for CommonGround (@{user.username}):\n\n{link}\n\n"
        f"The link works for {settings.EMAIL_LINK_MAX_AGE_SECONDS // 86400} days. "
        "If you didn't create this account, you can ignore this email.\n"
    ))


def send_email_change_confirmation(user, new_email):
    link = frontend_link("/verify-email", token=make_email_token(user, "change", new_email))
    sent = _send(new_email, "confirm your new email address", (
        f"Hi {user.first_name or user.username},\n\n"
        f"Someone asked to use this address for the CommonGround account @{user.username}. "
        f"Open this link to confirm:\n\n{link}\n\n"
        "If this wasn't you, ignore this email and nothing will change.\n"
    ))
    if user.email:
        _send(user.email, "email change requested", (
            f"Hi {user.first_name or user.username},\n\n"
            f"Someone asked to change the email on your CommonGround account to {mask_email(new_email)}. "
            "It changes only after the new address is confirmed.\n\n"
            "If this wasn't you, change your password now.\n"
        ))
    return sent


def send_password_reset_email(user):
    return _send(user.email, "reset your password", (
        f"Hi {user.first_name or user.username},\n\n"
        f"Someone asked to reset the password for @{user.username}. Open this link to choose a new one:\n\n"
        f"{make_reset_link(user)}\n\n"
        f"The link works for {settings.PASSWORD_RESET_TIMEOUT // 60} minutes and only once. "
        "If you didn't ask for this, ignore this email; your password stays the same.\n"
    ))


def send_password_changed_email(user):
    if not user.email:
        return False
    return _send(user.email, "your password was changed", (
        f"Hi {user.first_name or user.username},\n\n"
        "The password for your CommonGround account was just changed, and every device was signed out.\n\n"
        "If this wasn't you, reset your password right away:\n"
        f"{settings.FRONTEND_URL.rstrip('/')}/forgot-password\n"
    ))


def mask_email(email):
    local, _, domain = email.partition("@")
    return f"{local[:1]}{'•' * max(1, len(local) - 1)}@{domain}"


# ---------------------------------------------------------------- sessions

def revoke_all_sessions(user):
    """Reject every access and refresh token issued for this user until now."""
    now = timezone.now()
    UserProfile.objects.update_or_create(user=user, defaults={"sessions_revoked_at": now})
    cache.set(REVOKED_CACHE_KEY.format(user.pk), int(now.timestamp()), timeout=None)
    outstanding = OutstandingToken.objects.filter(user=user).exclude(blacklistedtoken__isnull=False)
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=token) for token in outstanding], ignore_conflicts=True,
    )
    return now


def revoked_before(user_id):
    """Unix second before which this user's tokens are void (0 = never revoked)."""
    key = REVOKED_CACHE_KEY.format(user_id)
    value = cache.get(key)
    if value is None:
        revoked_at = UserProfile.objects.filter(user_id=user_id).values_list("sessions_revoked_at", flat=True).first()
        value = int(revoked_at.timestamp()) if revoked_at else 0
        cache.set(key, value, timeout=3600)
    return value


def token_is_revoked(token):
    """True when a token (access or refresh) was issued before the user's last revocation.

    JWT "iat" has whole-second precision, so the cut-off is the start of the
    revoking second: tokens issued for the user in that same second (the new
    session after a password change) stay valid.
    """
    user_id = token.get(settings.SIMPLE_JWT.get("USER_ID_CLAIM", "user_id"))
    issued = token.get("iat")
    if user_id is None or issued is None:
        return False
    return int(issued) < revoked_before(user_id)


class RevocableJWTAuthentication(JWTAuthentication):
    """JWTAuthentication that also rejects access tokens from revoked sessions."""

    def get_user(self, validated_token):
        if token_is_revoked(validated_token):
            raise AuthenticationFailed("This session was signed out. Please sign in again.", code="session_revoked")
        return super().get_user(validated_token)
