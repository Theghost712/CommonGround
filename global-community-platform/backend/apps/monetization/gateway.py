"""Payment gateways.

Flutterwave hosted checkout takes M-Pesa, Mixx by Yas (Tigo Pesa), Airtel Money and
HaloPesa in Tanzania, plus cards, on a page Flutterwave hosts. We never see card
details or mobile money PINs.

Never trust what the browser or a webhook *says* about a payment: `verify` asks the
gateway directly, and the amount and currency must match what we asked for.

Without FLUTTERWAVE_SECRET_KEY, development (DEBUG) uses a test gateway that pays
instantly, so the whole flow can be tried locally. Production refuses payments
until the key is set.
"""
import hmac
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings

logger = logging.getLogger(__name__)


class PaymentsUnavailable(Exception):
    """Payments are not configured on this server."""


class GatewayError(Exception):
    """The gateway refused or could not be reached."""


@dataclass
class Verification:
    status: str  # "successful", "failed" or "pending"
    amount: int = 0
    currency: str = ""
    transaction_id: str = ""
    payment_type: str = ""
    reason: str = ""


class TestGateway:
    """Development only: the checkout link goes straight back to the app, already paid."""

    name = "test"

    def checkout(self, payment, user, redirect_url, title):
        query = urllib.parse.urlencode({"tx_ref": payment.reference, "status": "successful"})
        return f"{redirect_url}{'&' if '?' in redirect_url else '?'}{query}"

    def verify(self, payment):
        return Verification("successful", payment.amount, payment.currency, f"test-{payment.pk}", "test")

    def webhook_is_authentic(self, request):
        return False


class FlutterwaveGateway:
    name = "flutterwave"
    base_url = "https://api.flutterwave.com/v3"

    def __init__(self, secret_key, secret_hash="", payment_options="", timeout=20):
        self.secret_key = secret_key
        self.secret_hash = secret_hash
        self.payment_options = payment_options
        self.timeout = timeout

    def _call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base_url + path, data=data, method=method)
        request.add_header("Authorization", f"Bearer {self.secret_key}")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read() or b"{}")
            except ValueError:
                detail = {}
            if error.code == 404 or (detail.get("message") or "").lower().startswith("no transaction"):
                return detail | {"status": "error", "_not_found": True}
            logger.warning("Flutterwave %s %s failed: %s %s", method, path, error.code, detail.get("message"))
            raise GatewayError(detail.get("message") or f"Payment provider error {error.code}") from error
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            logger.warning("Flutterwave %s %s unreachable: %s", method, path, error)
            raise GatewayError("The payment provider could not be reached. Please try again.") from error

    def checkout(self, payment, user, redirect_url, title):
        profile = getattr(user, "profile", None)
        customer = {"email": user.email, "name": user.get_full_name() or user.username}
        if profile is not None and profile.phone_number:
            customer["phone_number"] = profile.phone_number
        body = {
            "tx_ref": payment.reference,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "redirect_url": redirect_url,
            "customer": customer,
            "customizations": {"title": "CommonGround", "description": title[:100]},
            "meta": {"purpose": payment.purpose, "payment_id": str(payment.pk)},
        }
        if self.payment_options:
            body["payment_options"] = self.payment_options
        result = self._call("POST", "/payments", body)
        link = (result.get("data") or {}).get("link")
        if result.get("status") != "success" or not link:
            raise GatewayError(result.get("message") or "Could not start the payment.")
        return link

    def verify(self, payment):
        result = self._call("GET", "/transactions/verify_by_reference?" + urllib.parse.urlencode({"tx_ref": payment.reference}))
        if result.get("_not_found"):
            return Verification("pending")  # the customer hasn't paid (yet)
        data = result.get("data") or {}
        if result.get("status") != "success" or data.get("tx_ref") != payment.reference:
            return Verification("pending", reason=result.get("message", ""))
        status = data.get("status")
        verification = Verification(
            "successful" if status == "successful" else "failed" if status == "failed" else "pending",
            amount=int(float(data.get("amount") or 0)),
            currency=data.get("currency") or "",
            transaction_id=str(data.get("id") or ""),
            payment_type=str(data.get("payment_type") or "")[:40],
            reason=str(data.get("processor_response") or "")[:300],
        )
        return verification

    def webhook_is_authentic(self, request):
        signature = request.headers.get("verif-hash", "")
        return bool(self.secret_hash) and hmac.compare_digest(signature, self.secret_hash)


def get_gateway():
    key = getattr(settings, "FLUTTERWAVE_SECRET_KEY", "")
    if key:
        return FlutterwaveGateway(key, settings.FLUTTERWAVE_SECRET_HASH, settings.FLUTTERWAVE_PAYMENT_OPTIONS)
    if settings.DEBUG and settings.DJANGO_ENV != "production":
        return TestGateway()
    raise PaymentsUnavailable("Payments are not set up on this server yet.")


def payments_enabled():
    try:
        get_gateway()
    except PaymentsUnavailable:
        return False
    return True
