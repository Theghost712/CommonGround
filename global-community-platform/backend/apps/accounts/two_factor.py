"""Two-factor sign-in with an authenticator app (TOTP, RFC 6238) plus one-use recovery codes.

Flow:
1. POST /auth/2fa/setup/ {password}        -> secret + otpauth:// URI (not active yet)
2. POST /auth/2fa/confirm/ {code}          -> active; returns 10 recovery codes once
3. Sign-in: POST /auth/token/ answers {two_factor_required, challenge} instead of tokens;
   POST /auth/token/2fa/ {challenge, code} -> tokens. A recovery code works in place of `code`.
4. POST /auth/2fa/disable/ {password, code} and /auth/2fa/recovery-codes/ {password, code}.

The TOTP secret is encrypted with a key derived from TWO_FACTOR_ENCRYPTION_KEY
(default: SECRET_KEY). Changing that key makes stored secrets unreadable, so
everyone with 2FA would have to sign in with a recovery code and set it up again.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import TwoFactorAuth

User = get_user_model()

STEP_SECONDS = 30
DIGITS = 6
RECOVERY_CODE_COUNT = 10
CHALLENGE_SALT = "accounts.2fa-login"
CHALLENGE_MAX_AGE = 300
CHALLENGE_MAX_FAILURES = 5
# Across all challenges: someone who knows the password could otherwise keep asking
# for fresh challenges. After this many wrong codes the account's second step pauses.
USER_MAX_FAILURES = 10
USER_LOCK_SECONDS = 15 * 60
ISSUER = "CommonGround"


# ---------------------------------------------------------------- secret storage

def _fernet():
    key = getattr(settings, "TWO_FACTOR_ENCRYPTION_KEY", "") or settings.SECRET_KEY
    digest = hashlib.sha256(f"commonground-2fa:{key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(secret_b32):
    return _fernet().encrypt(secret_b32.encode()).decode()


def decrypt_secret(token):
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


# ---------------------------------------------------------------- TOTP

def _b32decode(secret_b32):
    padded = secret_b32.upper() + "=" * (-len(secret_b32) % 8)
    return base64.b32decode(padded)


def totp(secret_b32, step):
    digest = hmac.new(_b32decode(secret_b32), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def current_step(now=None):
    return int((now if now is not None else time.time()) // STEP_SECONDS)


def match_totp(secret_b32, code, after_step=0, now=None):
    """Return the time step `code` belongs to (±1 step for clock drift), or None.

    Steps at or before `after_step` are refused, so each code works only once.
    """
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != DIGITS:
        return None
    step = current_step(now)
    for candidate in (step - 1, step, step + 1):
        if candidate > after_step and constant_time_compare(totp(secret_b32, candidate), code):
            return candidate
    return None


def otpauth_uri(user, secret_b32):
    label = quote(f"{ISSUER}:{user.username}")
    return f"otpauth://totp/{label}?" + urlencode({
        "secret": secret_b32, "issuer": ISSUER, "algorithm": "SHA1", "digits": DIGITS, "period": STEP_SECONDS,
    })


# ---------------------------------------------------------------- recovery codes

_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i


def _normalise_recovery(code):
    return "".join(ch for ch in str(code).lower() if ch in _RECOVERY_ALPHABET)


def _hash_recovery(code):
    return salted_hmac("accounts.2fa-recovery", _normalise_recovery(code), algorithm="sha256").hexdigest()


def new_recovery_codes():
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes, [_hash_recovery(code) for code in codes]


# ---------------------------------------------------------------- checking a code

def get_enabled(user):
    return TwoFactorAuth.objects.filter(user=user, confirmed_at__isnull=False).first()


def is_enabled(user):
    return TwoFactorAuth.objects.filter(user=user, confirmed_at__isnull=False).exists()


def verify_code(user, code):
    """Check an authenticator code or a recovery code for a user with 2FA on.

    Returns "totp", "recovery" or None. Uses up the code it accepts.
    """
    code = str(code or "").strip()
    if not code:
        return None
    with transaction.atomic():
        device = TwoFactorAuth.objects.select_for_update().filter(user=user, confirmed_at__isnull=False).first()
        if device is None:
            return None
        secret = decrypt_secret(device.secret_encrypted)
        compact = code.replace(" ", "").replace("-", "")
        if compact.isdigit() and len(compact) == DIGITS:
            step = match_totp(secret, compact, after_step=device.last_used_step) if secret else None
            if step is not None:
                device.last_used_step = step
                device.save(update_fields=["last_used_step", "updated_at"])
                return "totp"
            return None
        hashed = _hash_recovery(code)
        if len(_normalise_recovery(code)) == 10 and hashed in device.recovery_code_hashes:
            device.recovery_code_hashes = [h for h in device.recovery_code_hashes if h != hashed]
            device.save(update_fields=["recovery_code_hashes", "updated_at"])
            return "recovery"
    return None


# ---------------------------------------------------------------- sign-in challenge

def make_login_challenge(user):
    return signing.dumps({"u": user.pk, "n": secrets.token_urlsafe(12)}, salt=CHALLENGE_SALT, compress=True)


def read_login_challenge(challenge):
    try:
        payload = signing.loads(challenge, salt=CHALLENGE_SALT, max_age=CHALLENGE_MAX_AGE)
    except (signing.BadSignature, TypeError):
        return None, None
    user = User.objects.filter(pk=payload.get("u"), is_active=True).first()
    return user, payload.get("n")


# ---------------------------------------------------------------- emails

def _notify(user, subject, body):
    from .security import _send

    if user.email:
        _send(user.email, subject, f"Hi {user.first_name or user.username},\n\n{body}\n")


def _bump(key, timeout):
    """Increment a cache counter, starting it at 1; returns the new value."""
    if cache.add(key, 1, timeout=timeout):
        return 1
    try:
        return cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, timeout=timeout)
        return 1


def no_store(response):
    response["Cache-Control"] = "no-store"
    return response


def _password_ok(request):
    return request.user.check_password(str(request.data.get("password", "")))


WRONG_PASSWORD = {"password": ["Your password is not correct."]}
WRONG_CODE = {"code": ["That code didn't work. Check the time on your phone, or use a recovery code."]}


# ---------------------------------------------------------------- views

class TwoFactorStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        device = get_enabled(request.user)
        return no_store(Response({
            "enabled": device is not None,
            "confirmed_at": device.confirmed_at if device else None,
            "recovery_codes_left": len(device.recovery_code_hashes) if device else 0,
        }))


@method_decorator(csrf_protect, name="dispatch")
class TwoFactorSetupView(APIView):
    """POST {password}. Starts (or restarts) setup; 2FA stays off until confirmed."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        if not _password_ok(request):
            return Response(WRONG_PASSWORD, status=status.HTTP_400_BAD_REQUEST)
        if is_enabled(request.user):
            return Response({"detail": "Two-step sign-in is already on."}, status=status.HTTP_400_BAD_REQUEST)
        secret = new_secret()
        TwoFactorAuth.objects.update_or_create(user=request.user, defaults={
            "secret_encrypted": encrypt_secret(secret), "confirmed_at": None,
            "last_used_step": 0, "recovery_code_hashes": [],
        })
        return no_store(Response({"secret": secret, "otpauth_uri": otpauth_uri(request.user, secret)}))


@method_decorator(csrf_protect, name="dispatch")
class TwoFactorConfirmView(APIView):
    """POST {code}. Turns 2FA on and returns the recovery codes (shown once)."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        device = TwoFactorAuth.objects.filter(user=request.user, confirmed_at__isnull=True).first()
        if device is None:
            return Response({"detail": "Start setup first."}, status=status.HTTP_400_BAD_REQUEST)
        secret = decrypt_secret(device.secret_encrypted)
        step = match_totp(secret, request.data.get("code", "")) if secret else None
        if step is None:
            return Response({"code": ["That code didn't match. Type the 6 digits your app shows now."]},
                            status=status.HTTP_400_BAD_REQUEST)
        codes, hashes = new_recovery_codes()
        device.confirmed_at = timezone.now()
        device.last_used_step = step
        device.recovery_code_hashes = hashes
        device.save()
        _notify(request.user, "two-step sign-in is on",
                "Two-step sign-in was turned on for your CommonGround account. From now on, signing in needs "
                "a code from your authenticator app.\n\nIf this wasn't you, reset your password right away.")
        return no_store(Response({"enabled": True, "recovery_codes": codes}))


@method_decorator(csrf_protect, name="dispatch")
class TwoFactorDisableView(APIView):
    """POST {password, code}."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        if not _password_ok(request):
            return Response(WRONG_PASSWORD, status=status.HTTP_400_BAD_REQUEST)
        if not is_enabled(request.user):
            TwoFactorAuth.objects.filter(user=request.user).delete()
            return no_store(Response({"enabled": False}))
        if verify_code(request.user, request.data.get("code")) is None:
            return Response(WRONG_CODE, status=status.HTTP_400_BAD_REQUEST)
        TwoFactorAuth.objects.filter(user=request.user).delete()
        _notify(request.user, "two-step sign-in was turned off",
                "Two-step sign-in was turned off for your CommonGround account.\n\n"
                "If this wasn't you, reset your password and turn it back on.")
        return no_store(Response({"enabled": False}))


@method_decorator(csrf_protect, name="dispatch")
class TwoFactorRecoveryCodesView(APIView):
    """POST {password, code}. Replaces every recovery code with 10 new ones."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        if not _password_ok(request):
            return Response(WRONG_PASSWORD, status=status.HTTP_400_BAD_REQUEST)
        if not is_enabled(request.user):
            return Response({"detail": "Two-step sign-in is off."}, status=status.HTTP_400_BAD_REQUEST)
        if verify_code(request.user, request.data.get("code")) is None:
            return Response(WRONG_CODE, status=status.HTTP_400_BAD_REQUEST)
        codes, hashes = new_recovery_codes()
        TwoFactorAuth.objects.filter(user=request.user).update(recovery_code_hashes=hashes, updated_at=timezone.now())
        return no_store(Response({"recovery_codes": codes}))


@method_decorator(csrf_protect, name="dispatch")
class TwoFactorLoginView(APIView):
    """POST {challenge, code}: the second sign-in step. Sets the refresh cookie like /auth/token/."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request):
        from .views import set_refresh_cookie

        expired = Response({"detail": "This sign-in attempt expired. Enter your password again.", "code": "challenge_expired"},
                           status=status.HTTP_401_UNAUTHORIZED)
        user, nonce = read_login_challenge(str(request.data.get("challenge", "")))
        if user is None:
            return expired
        failures_key = f"2fa-login-failures:{nonce}"
        used_key = f"2fa-login-used:{nonce}"
        user_key = f"2fa-user-failures:{user.pk}"
        if (cache.get(user_key) or 0) >= USER_MAX_FAILURES:
            return Response({"detail": "Too many wrong codes. Wait 15 minutes, then sign in again.", "code": "two_factor_locked"},
                            status=status.HTTP_429_TOO_MANY_REQUESTS)
        if cache.get(used_key) or (cache.get(failures_key) or 0) >= CHALLENGE_MAX_FAILURES:
            return expired
        method = verify_code(user, request.data.get("code"))
        if method is None:
            _bump(failures_key, CHALLENGE_MAX_AGE)
            if _bump(user_key, USER_LOCK_SECONDS) == USER_MAX_FAILURES:
                _notify(user, "someone may know your password",
                        "Someone typed your CommonGround password correctly but then entered several wrong "
                        "two-step codes, so sign-in is paused for 15 minutes.\n\n"
                        "If this wasn't you, change your password now.")
            return Response(WRONG_CODE, status=status.HTTP_400_BAD_REQUEST)
        cache.delete(user_key)
        if not cache.add(used_key, 1, timeout=CHALLENGE_MAX_AGE):
            return expired
        refresh = RefreshToken.for_user(user)
        if settings.SIMPLE_JWT.get("UPDATE_LAST_LOGIN"):
            update_last_login(None, user)
        body = {"access": str(refresh.access_token)}
        if method == "recovery":
            left = len(get_enabled(user).recovery_code_hashes)
            body["recovery_codes_left"] = left
            _notify(user, "a recovery code was used",
                    f"A recovery code was used to sign in to your CommonGround account. You have {left} left.\n\n"
                    "If this wasn't you, change your password and create new recovery codes now.")
        response = Response(body)
        set_refresh_cookie(response, str(refresh))
        return no_store(response)
