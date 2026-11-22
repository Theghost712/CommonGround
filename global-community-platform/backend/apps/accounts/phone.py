"""Phone-number helpers for contact matching.

Numbers are normalised to international digits without "+" (e.g. "255712345678").
Only an HMAC of the number is used for matching, keyed with SECRET_KEY, so the
lookup column is useless on its own if the database leaks.
"""
import hashlib
import hmac
import re

from django.conf import settings

_KEEP = re.compile(r"[^\d+]")


def normalize_phone(raw, default_country_code=None):
    """Return the number as international digits, or None if it cannot be a phone number."""
    if not raw:
        return None
    cc = str(default_country_code or settings.DEFAULT_PHONE_COUNTRY_CODE).lstrip("+")
    value = _KEEP.sub("", str(raw).strip())
    if value.startswith("+"):
        digits = value[1:]
    elif value.startswith("00"):
        digits = value[2:]
    elif value.startswith("0"):
        digits = cc + value[1:]
    else:
        digits = value if len(value) > 9 else cc + value
    digits = digits.replace("+", "")
    if not digits.isdigit() or not 8 <= len(digits) <= 15:
        return None
    return digits


def phone_hash(normalized):
    if not normalized:
        return ""
    key = f"commonground-phone:{settings.SECRET_KEY}".encode("utf-8")
    return hmac.new(key, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
