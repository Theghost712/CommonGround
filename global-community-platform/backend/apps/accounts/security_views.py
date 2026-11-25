"""Account-security endpoints: password reset/change, email verification/change, sign out everywhere."""
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserProfile
from .security import (
    mask_email, read_email_token, revoke_all_sessions, send_email_change_confirmation,
    send_password_changed_email, send_password_reset_email, send_verification_email, user_from_reset,
)
from .views import clear_refresh_cookie, set_refresh_cookie

User = get_user_model()

RESET_SENT = "If an account matches, we've sent a link to its email address. Check your inbox and spam folder."


def no_store(response):
    response["Cache-Control"] = "no-store"
    return response


def check_new_password(user, new_password, confirm):
    if new_password != confirm:
        raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})
    try:
        validate_password(new_password, user)
    except DjangoValidationError as error:
        raise serializers.ValidationError({"new_password": list(error.messages)})


def email_taken(email, exclude_user=None):
    others = User.objects.filter(email__iexact=email)
    if exclude_user is not None:
        others = others.exclude(pk=exclude_user.pk)
    return others.exists()


class SecurityThrottleMixin:
    throttle_classes = [AnonRateThrottle, UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "account_email"


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetRequestView(SecurityThrottleMixin, APIView):
    """POST {login}: username or email. Always answers the same way (no account probing)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        login = str(request.data.get("login") or request.data.get("email") or "").strip()
        if not login:
            return Response({"login": ["Enter your username or email address."]}, status=status.HTTP_400_BAD_REQUEST)
        field = "email__iexact" if "@" in login else "username__iexact"
        for user in User.objects.filter(**{field: login}, is_active=True).exclude(email="")[:5]:
            if user.has_usable_password():
                send_password_reset_email(user)
        return no_store(Response({"detail": RESET_SENT}))


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetConfirmView(SecurityThrottleMixin, APIView):
    """POST {uid, token, new_password, new_password_confirm}."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "auth"

    def post(self, request):
        user = user_from_reset(str(request.data.get("uid", "")), str(request.data.get("token", "")))
        if user is None:
            return Response(
                {"detail": "This reset link is invalid or has expired. Please ask for a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        check_new_password(user, str(request.data.get("new_password", "")), str(request.data.get("new_password_confirm", "")))
        with transaction.atomic():
            user.set_password(request.data["new_password"])
            user.save(update_fields=["password"])
            # The link reached their inbox, so the address is proven too.
            UserProfile.objects.filter(user=user, email_verified_at__isnull=True).update(email_verified_at=timezone.now())
            revoke_all_sessions(user)
        send_password_changed_email(user)
        return no_store(clear_refresh_cookie(Response({"detail": "Your password was reset. Sign in with the new password."})))


@method_decorator(csrf_protect, name="dispatch")
class PasswordChangeView(APIView):
    """POST {current_password, new_password, new_password_confirm}. Signs out every other device."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        user = request.user
        if not user.check_password(str(request.data.get("current_password", ""))):
            return Response({"current_password": ["Your current password is not correct."]}, status=status.HTTP_400_BAD_REQUEST)
        new_password = str(request.data.get("new_password", ""))
        if user.check_password(new_password):
            return Response({"new_password": ["Choose a password you aren't using now."]}, status=status.HTTP_400_BAD_REQUEST)
        check_new_password(user, new_password, str(request.data.get("new_password_confirm", "")))
        with transaction.atomic():
            user.set_password(new_password)
            user.save(update_fields=["password"])
            revoke_all_sessions(user)
        send_password_changed_email(user)
        # This device stays signed in with a fresh session.
        refresh = RefreshToken.for_user(user)
        response = Response({"access": str(refresh.access_token), "detail": "Password changed. Other devices were signed out."})
        set_refresh_cookie(response, str(refresh))
        return no_store(response)


@method_decorator(csrf_protect, name="dispatch")
class SignOutEverywhereView(APIView):
    """POST {keep_current: bool}. Revokes every session; optionally re-issues one for this device."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        revoke_all_sessions(request.user)
        if request.data.get("keep_current"):
            refresh = RefreshToken.for_user(request.user)
            response = Response({"access": str(refresh.access_token), "detail": "Signed out of all other devices."})
            set_refresh_cookie(response, str(refresh))
            return no_store(response)
        return no_store(clear_refresh_cookie(Response({"detail": "Signed out of all devices."})))


@method_decorator(csrf_protect, name="dispatch")
class EmailVerifyView(APIView):
    """POST {token}. Works signed in or out: the signed link is the proof."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        user, payload = read_email_token(str(request.data.get("token", "")))
        if user is None:
            return Response(
                {"detail": "This confirmation link is invalid, expired or already used. Ask for a new one from Account security."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if payload.get("p") == "change":
            new_email = payload.get("n", "")
            if email_taken(new_email, exclude_user=user):
                return Response({"detail": "That email address is now used by another account."}, status=status.HTTP_400_BAD_REQUEST)
            user.email = new_email
            user.save(update_fields=["email"])
            message = f"Your email is now {new_email}."
        else:
            message = "Thanks! Your email address is confirmed."
        UserProfile.objects.update_or_create(user=user, defaults={"email_verified_at": timezone.now()})
        return no_store(Response({"detail": message, "email": user.email}))


@method_decorator(csrf_protect, name="dispatch")
class EmailVerificationResendView(SecurityThrottleMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.email:
            return Response({"detail": "Add an email address first."}, status=status.HTTP_400_BAD_REQUEST)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if profile.email_verified_at:
            return Response({"detail": "Your email address is already confirmed."})
        send_verification_email(user)
        return Response({"detail": f"We sent a new link to {mask_email(user.email)}."})


@method_decorator(csrf_protect, name="dispatch")
class EmailChangeView(SecurityThrottleMixin, APIView):
    """POST {new_email, password}. The address changes only after the new inbox confirms it."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.check_password(str(request.data.get("password", ""))):
            return Response({"password": ["Your password is not correct."]}, status=status.HTTP_400_BAD_REQUEST)
        field = serializers.EmailField()
        try:
            new_email = field.run_validation(str(request.data.get("new_email", "")).strip())
        except serializers.ValidationError as error:
            return Response({"new_email": error.detail}, status=status.HTTP_400_BAD_REQUEST)
        if new_email.lower() == user.email.lower():
            return Response({"new_email": ["That is already your email address."]}, status=status.HTTP_400_BAD_REQUEST)
        if email_taken(new_email, exclude_user=user):
            return Response({"new_email": ["Another account already uses this email address."]}, status=status.HTTP_400_BAD_REQUEST)
        send_email_change_confirmation(user, new_email)
        return Response({"detail": f"Check {new_email} and open the link to finish the change."})


@method_decorator(csrf_protect, name="dispatch")
class AccountDeleteView(APIView):
    """POST {password, code?, confirm: "DELETE"}: permanently delete your account.

    With two-step sign-in on, an authenticator or recovery code is required too.
    Communities and group chats you created are handed to another member.
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        from .deletion import delete_account
        from .two_factor import is_enabled, verify_code

        user = request.user
        if str(request.data.get("confirm", "")).strip().upper() != "DELETE":
            return Response({"confirm": ['Type DELETE to confirm.']}, status=status.HTTP_400_BAD_REQUEST)
        # Accounts made with "Sign in with Google" have no password: the typed
        # confirmation (and the 2FA code, if on) is the check.
        if user.has_usable_password() and not user.check_password(str(request.data.get("password", ""))):
            return Response({"password": ["Your password is not correct."]}, status=status.HTTP_400_BAD_REQUEST)
        if is_enabled(user) and verify_code(user, request.data.get("code")) is None:
            return Response({"code": ["Enter a code from your authenticator app (or a recovery code)."]}, status=status.HTTP_400_BAD_REQUEST)
        if user.is_superuser and not User.objects.filter(is_superuser=True, is_active=True).exclude(pk=user.pk).exists():
            return Response({"detail": "You're the only administrator. Make someone else an administrator first."}, status=status.HTTP_409_CONFLICT)
        delete_account(user)
        return no_store(clear_refresh_cookie(Response({"detail": "Your account and everything in it have been deleted."})))
