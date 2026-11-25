"""Sign in with Google (Google Identity Services).

The browser shows Google's button; Google returns a signed ID token (a JWT) which the
browser posts here. We verify it with Google's published keys (signature, audience =
our client id, issuer, expiry, email_verified), then:

1. a linked account (same Google "sub")      → sign in;
2. an account with the same confirmed-at-Google email → link it and sign in;
3. otherwise                                  → create an account (email marked
   confirmed, no password; one can be set later with "Forgot password").

Two-step sign-in, suspensions and the invite link behave exactly like a password
sign-in (apps.accounts.views.complete_sign_in). Switched on by GOOGLE_CLIENT_ID.
"""

import re

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from .models import SocialLogin, UserProfile

User = get_user_model()
GOOGLE_CERTS = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
_jwks = None


class GoogleTokenError(Exception):
    pass


def verify_google_token(token):
    """Return the token's claims, or raise GoogleTokenError."""
    global _jwks
    client_id = settings.GOOGLE_CLIENT_ID
    if not client_id:
        raise GoogleTokenError("Google sign-in isn't set up on this server.")
    try:
        if _jwks is None:
            _jwks = jwt.PyJWKClient(GOOGLE_CERTS, cache_keys=True, lifespan=6 * 3600)
        key = _jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=client_id, options={"require": ["exp", "iat", "sub", "aud", "iss"]}, leeway=60)
    except (jwt.PyJWTError, ValueError) as error:
        raise GoogleTokenError("Google couldn't confirm this sign-in. Please try again.") from error
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleTokenError("Google couldn't confirm this sign-in. Please try again.")
    if not claims.get("email") or not claims.get("email_verified"):
        raise GoogleTokenError("Your Google account's email isn't verified.")
    return claims


def _username_for(claims):
    from .serializers import RegisterSerializer

    reserved = {name.lower() for name in RegisterSerializer.RESERVED_USERNAMES}
    base = re.sub(r"[^a-zA-Z0-9_.]", "", claims["email"].split("@", 1)[0])[:24] or "member"
    if base.lower() in reserved or len(base) < 3:
        base = f"{base}_cg"[:24]
    candidate, n = base, 1
    while User.objects.filter(username__iexact=candidate).exists():
        n += 1
        candidate = f"{base}{n}"
    return candidate


def account_for(claims, invited_by=""):
    """Find, link or create the account for verified Google claims."""
    sub, email = str(claims["sub"]), claims["email"].strip().lower()
    link = SocialLogin.objects.select_related("user").filter(provider=SocialLogin.GOOGLE, uid=sub).first()
    if link:
        SocialLogin.objects.filter(pk=link.pk).update(last_used_at=timezone.now(), email=email)
        return link.user, False
    user = User.objects.filter(email__iexact=email).order_by("pk").first()
    created = False
    with transaction.atomic():
        if user is None:
            user = User(username=_username_for(claims), email=email,
                        first_name=(claims.get("given_name") or "")[:150], last_name=(claims.get("family_name") or "")[:150])
            user.set_unusable_password()
            user.save()
            created = True
        UserProfile.objects.update_or_create(user=user, defaults={"email_verified_at": timezone.now()})
        try:
            SocialLogin.objects.create(user=user, provider=SocialLogin.GOOGLE, uid=sub, email=email, last_used_at=timezone.now())
        except IntegrityError:
            pass
    if created:
        picture = claims.get("picture") or ""
        if picture.startswith("https://"):
            UserProfile.objects.filter(user=user, avatar_url="").update(avatar_url=picture[:500])
        if invited_by:
            try:
                from apps.social.invites import welcome_invited_user

                welcome_invited_user(user, invited_by)
            except Exception:
                pass
    return user, created


@method_decorator(csrf_protect, name="dispatch")
class GoogleSignInView(APIView):
    """POST {credential, invited_by?} → same answers as /auth/token/ (+ "created")."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        from .views import complete_sign_in

        try:
            claims = verify_google_token(str(request.data.get("credential", "")))
        except GoogleTokenError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        user, created = account_for(claims, str(request.data.get("invited_by", ""))[:150])
        if not user.is_active:
            return Response({"detail": "This account is disabled."}, status=status.HTTP_403_FORBIDDEN)
        response = complete_sign_in(user)
        if response.status_code == 200 and isinstance(response.data, dict):
            response.data["created"] = created
        return response


class AuthProvidersView(APIView):
    """GET /auth/providers/ → which extra sign-in options the site offers."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"google_client_id": settings.GOOGLE_CLIENT_ID or ""})
