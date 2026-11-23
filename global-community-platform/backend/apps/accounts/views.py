import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import update_last_login
from django.core.cache import cache
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserProfile
from .security import token_is_revoked
from .serializers import RegisterSerializer, UserProfileSerializer, UserSerializer


@method_decorator(csrf_protect, name="dispatch")
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle, UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "auth"


@ensure_csrf_cookie
def csrf_cookie(request):
    return JsonResponse({"csrfToken": get_token(request)})


def set_refresh_cookie(response, token):
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        path=settings.REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response):
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH,
                           samesite=settings.REFRESH_COOKIE_SAMESITE)
    return response


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle, UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        # Check the password only; tokens are issued below once every check passes.
        serializer = TokenObtainSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        from apps.moderation.services import active_suspension

        suspension = active_suspension(serializer.user)
        if suspension:
            until, reason = suspension
            # The password was right, so it's safe to say why sign-in is refused.
            return Response({
                "detail": f"Your account is suspended until {until:%d %b %Y, %H:%M} UTC." + (f" Reason: {reason}" if reason else ""),
                "code": "account_suspended", "suspended_until": until,
            }, status=status.HTTP_403_FORBIDDEN)
        from .two_factor import is_enabled, make_login_challenge

        if is_enabled(serializer.user):
            # Password is right; no tokens until the second step (/auth/token/2fa/).
            response = Response({"two_factor_required": True, "challenge": make_login_challenge(serializer.user)})
            response["Cache-Control"] = "no-store"
            return response
        refresh = RefreshToken.for_user(serializer.user)
        if settings.SIMPLE_JWT.get("UPDATE_LAST_LOGIN"):
            update_last_login(None, serializer.user)
        response = Response({"access": str(refresh.access_token)})
        set_refresh_cookie(response, str(refresh))
        response["Cache-Control"] = "no-store"
        return response


@method_decorator(csrf_protect, name="dispatch")
class RefreshView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if not refresh:
            return Response({"detail": "Refresh cookie required."}, status=status.HTTP_401_UNAUTHORIZED)
        revoked = Response({"detail": "Refresh token is invalid or revoked."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            # Sessions from before a password change or "sign out everywhere" are dead,
            # even if their refresh token was never written to the outstanding list.
            if token_is_revoked(RefreshToken(refresh)):
                return clear_refresh_cookie(revoked)
        except TokenError:
            return revoked
        serializer = TokenRefreshSerializer(data={"refresh": refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError:
            return revoked
        response = Response({"access": serializer.validated_data["access"]})
        if rotated := serializer.validated_data.get("refresh"):
            set_refresh_cookie(response, rotated)
        response["Cache-Control"] = "no-store"
        return response


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except TokenError:
                # Logout still clears the cookie when it is expired or malformed.
                pass
        response = clear_refresh_cookie(Response(status=status.HTTP_204_NO_CONTENT))
        response["Cache-Control"] = "no-store"
        return response


class WebSocketTicketView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not request.user.is_active:
            return Response({"detail": "Active account required."}, status=status.HTTP_401_UNAUTHORIZED)
        ticket = secrets.token_urlsafe(32)
        digest = hashlib.sha256(ticket.encode()).hexdigest()
        cache.set(
            f"ws-ticket:{digest}",
            {"id": request.user.pk, "username": request.user.get_username(), "is_active": True},
            timeout=settings.WEBSOCKET_TICKET_TTL_SECONDS,
        )
        response = Response({"ticket": ticket})
        response["Cache-Control"] = "no-store"
        return response


class CurrentUserView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        return profile
