from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile
from apps.communities.models import Community
from apps.discussions.models import Discussion
from apps.notifications.models import Notification
from apps.safety.models import Block

from . import services
from .gateway import FlutterwaveGateway, GatewayError, Verification
from .models import LedgerEntry, Payment, PayoutRequest, Promotion, Referral, Tip

User = get_user_model()
TEST_GATEWAY = override_settings(DEBUG=True, TIP_PLATFORM_FEE_PERCENT=10, PROMOTION_DAILY_PRICE=3000, PROMOTION_AUTO_APPROVE=False, REFERRAL_REWARD_AMOUNT=1000)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def make_user(username, verified=True):
    user = User.objects.create_user(username, email=f"{username}@example.com", password="Strong-pass-123")
    UserProfile.objects.create(user=user, email_verified_at=timezone.now() if verified else None)
    return user


class FakeGateway:
    """Lets a test decide what the gateway reports."""

    name = "fake"

    def __init__(self, verification):
        self.verification = verification

    def checkout(self, payment, user, redirect_url, title):
        return f"https://pay.example/{payment.reference}"

    def verify(self, payment):
        return self.verification

    def webhook_is_authentic(self, request):
        return request.headers.get("verif-hash") == "s3cret"


def using(gateway):
    return mock.patch("apps.monetization.services.get_gateway", return_value=gateway)


@TEST_GATEWAY
class TipTests(TestCase):
    def setUp(self):
        self.fan = make_user("fan")
        self.creator = make_user("creator")
        self.post = Discussion.objects.create(author=self.creator, title="My song", body="Listen")

    def test_tip_flow_credits_creator_minus_fee_once(self):
        response = client_for(self.fan).post("/api/v1/tips/", {"discussion": self.post.pk, "amount": 5000, "message": "Great!"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        reference = response.data["reference"]
        self.assertIn(f"tx_ref={reference}", response.data["checkout_url"])
        self.assertEqual(services.balance(self.creator, LedgerEntry.EARNINGS), 0)  # not paid yet

        with self.captureOnCommitCallbacks(execute=True):
            for _ in range(2):  # returning twice must not pay twice
                status = client_for(self.fan).get(f"/api/v1/payments/{reference}/")
                self.assertEqual(status.data["status"], "successful")
        self.assertEqual(services.balance(self.creator, LedgerEntry.EARNINGS), 4500)
        tip = Tip.objects.get()
        self.assertEqual((tip.status, tip.platform_fee, tip.discussion_id), (Tip.PAID, 500, self.post.pk))
        self.assertTrue(Notification.objects.filter(recipient=self.creator, title__contains="tip of TZS 5,000").exists())

    def test_only_the_payer_can_check_a_payment(self):
        response = client_for(self.fan).post("/api/v1/tips/", {"username": "creator", "amount": 1000}, format="json")
        other = client_for(make_user("other")).get(f"/api/v1/payments/{response.data['reference']}/")
        self.assertEqual(other.status_code, 404)

    def test_rules(self):
        fan = client_for(self.fan)
        self.assertEqual(fan.post("/api/v1/tips/", {"username": "fan", "amount": 1000}, format="json").status_code, 400)
        self.assertEqual(fan.post("/api/v1/tips/", {"username": "creator", "amount": 100}, format="json").status_code, 400)
        Block.objects.create(blocker=self.creator, blocked=self.fan)
        self.assertEqual(fan.post("/api/v1/tips/", {"username": "creator", "amount": 1000}, format="json").status_code, 400)
        self.assertEqual(APIClient().post("/api/v1/tips/", {"username": "creator", "amount": 1000}, format="json").status_code, 401)

    def test_failed_or_short_payment_credits_nothing(self):
        for verification in [Verification("failed", reason="Cancelled"), Verification("successful", 100, "TZS", "1")]:
            with using(FakeGateway(verification)):
                tip, _ = services.start_tip(self.fan, self.creator, 2000)
                payment = services.confirm_payment(tip.payment)
            self.assertEqual(payment.status, Payment.FAILED)
            tip.refresh_from_db()
            self.assertEqual(tip.status, Tip.FAILED)
        self.assertEqual(services.balance(self.creator, LedgerEntry.EARNINGS), 0)

    def test_pending_payment_stays_pending(self):
        with using(FakeGateway(Verification("pending"))):
            tip, _ = services.start_tip(self.fan, self.creator, 2000)
            self.assertEqual(services.confirm_payment(tip.payment).status, Payment.PENDING)

    @override_settings(DEBUG=False)
    def test_production_without_key_refuses_payments(self):
        response = client_for(self.fan).post("/api/v1/tips/", {"username": "creator", "amount": 1000}, format="json")
        self.assertEqual(response.status_code, 503)
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(APIClient().get("/api/v1/money/config/").data["enabled"])


@TEST_GATEWAY
class WebhookTests(TestCase):
    def test_webhook_needs_the_secret_and_then_verifies_with_the_gateway(self):
        fan, creator = make_user("fan"), make_user("creator")
        gateway = FakeGateway(Verification("successful", 3000, "TZS", "99", "mobilemoneytz"))
        with using(gateway), mock.patch("apps.monetization.views.get_gateway", return_value=gateway):
            tip, _ = services.start_tip(fan, creator, 3000)
            body = {"event": "charge.completed", "data": {"tx_ref": tip.payment.reference, "status": "successful", "amount": 999999}}
            self.assertEqual(self.client.post("/api/v1/payments/webhook/flutterwave/", body, content_type="application/json").status_code, 401)
            response = self.client.post("/api/v1/payments/webhook/flutterwave/", body, content_type="application/json", headers={"verif-hash": "s3cret"})
        self.assertEqual(response.status_code, 200)
        tip.payment.refresh_from_db()
        self.assertEqual((tip.payment.status, tip.payment.payment_type), (Payment.SUCCESSFUL, "mobilemoneytz"))
        self.assertEqual(services.balance(creator, LedgerEntry.EARNINGS), 2700)  # amount comes from the gateway check, not the webhook

    def test_stale_pending_payments_are_settled_or_expired(self):
        fan, creator = make_user("fan"), make_user("creator")
        with using(FakeGateway(Verification("pending"))):
            tip, _ = services.start_tip(fan, creator, 1000)
            Payment.objects.filter(pk=tip.payment.pk).update(created_at=timezone.now() - timedelta(days=1, minutes=1))
            services.check_pending_payments()
        tip.refresh_from_db()
        self.assertEqual(tip.status, Tip.FAILED)


class FlutterwaveGatewayTests(TestCase):
    def setUp(self):
        self.user = make_user("payer")
        self.payment = Payment.objects.create(payer=self.user, purpose=Payment.TIP, amount=2000, currency="TZS", provider="flutterwave")
        self.gateway = FlutterwaveGateway("FLWSECK_TEST-x", "hash", "mobilemoneytanzania, card")

    def test_checkout_sends_reference_amount_and_methods(self):
        with mock.patch.object(self.gateway, "_call", return_value={"status": "success", "data": {"link": "https://checkout.flutterwave.com/x"}}) as call:
            link = self.gateway.checkout(self.payment, self.user, "https://app.example/pay/return", "Tip")
        self.assertEqual(link, "https://checkout.flutterwave.com/x")
        method, path, body = call.call_args.args
        self.assertEqual((method, path), ("POST", "/payments"))
        self.assertEqual((body["tx_ref"], body["amount"], body["currency"], body["payment_options"]), (self.payment.reference, "2000", "TZS", "mobilemoneytanzania, card"))

    def test_verify_reads_status_amount_and_reference(self):
        data = {"tx_ref": self.payment.reference, "status": "successful", "amount": 2000, "currency": "TZS", "id": 42, "payment_type": "mobilemoneytz"}
        with mock.patch.object(self.gateway, "_call", return_value={"status": "success", "data": data}):
            result = self.gateway.verify(self.payment)
        self.assertEqual((result.status, result.amount, result.currency, result.transaction_id), ("successful", 2000, "TZS", "42"))
        with mock.patch.object(self.gateway, "_call", return_value={"status": "success", "data": {**data, "tx_ref": "someone-else"}}):
            self.assertEqual(self.gateway.verify(self.payment).status, "pending")
        with mock.patch.object(self.gateway, "_call", return_value={"status": "error", "_not_found": True}):
            self.assertEqual(self.gateway.verify(self.payment).status, "pending")

    def test_checkout_error_is_reported(self):
        with mock.patch.object(self.gateway, "_call", side_effect=GatewayError("Invalid currency")):
            with self.assertRaises(GatewayError):
                self.gateway.checkout(self.payment, self.user, "https://x", "Tip")


@TEST_GATEWAY
class PayoutTests(TestCase):
    def setUp(self):
        self.creator = make_user("creator")
        services.add_entry(self.creator, LedgerEntry.EARNINGS, LedgerEntry.TIP_RECEIVED, 20000)
        self.staff = User.objects.create_user("staff", is_staff=True)

    def ask(self, amount, user=None):
        return client_for(user or self.creator).post("/api/v1/money/wallet/", {"amount": amount, "network": "mpesa", "phone_number": "0712 345 678", "account_name": "Creator Name"}, format="json")

    def test_payout_holds_money_and_staff_can_pay_or_return_it(self):
        response = self.ask(15000)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(services.balance(self.creator, LedgerEntry.EARNINGS), 5000)
        payout = PayoutRequest.objects.get()
        self.assertEqual(payout.phone_number, "255712345678")
        self.assertEqual(self.ask(5000).status_code, 400)  # one at a time
        self.assertTrue(services.reject_payout(payout, self.staff, "Name did not match"))
        self.assertFalse(services.reject_payout(payout, self.staff))  # only once
        self.assertEqual(services.balance(self.creator, LedgerEntry.EARNINGS), 20000)
        self.assertEqual(self.ask(20000).status_code, 201)
        self.assertTrue(services.mark_payout_paid(PayoutRequest.objects.get(status=PayoutRequest.REQUESTED), self.staff, "Receipt ABC"))
        self.assertEqual(services.balance(self.creator, LedgerEntry.EARNINGS), 0)

    def test_limits(self):
        self.assertEqual(self.ask(25000).status_code, 400)  # more than available
        self.assertEqual(self.ask(1000).status_code, 400)  # below minimum
        unverified = make_user("unverified", verified=False)
        services.add_entry(unverified, LedgerEntry.EARNINGS, LedgerEntry.TIP_RECEIVED, 20000)
        self.assertEqual(self.ask(10000, unverified).status_code, 400)

    def test_wallet_shows_balances(self):
        data = client_for(self.creator).get("/api/v1/money/wallet/").data
        self.assertEqual((data["earnings"], data["ad_credit"], data["currency"]), (20000, 0, "TZS"))


@TEST_GATEWAY
class PromotionTests(TestCase):
    def setUp(self):
        self.owner = make_user("owner")
        self.viewer = make_user("viewer")
        self.staff = User.objects.create_user("staff", is_staff=True)
        self.post = Discussion.objects.create(author=self.owner, title="Grand opening", body="Come visit")

    def promote(self, days=2, post=None):
        return client_for(self.owner).post("/api/v1/promotions/", {"discussion": (post or self.post).pk, "days": days}, format="json")

    def test_paid_promotion_waits_for_review_then_shows_in_feeds(self):
        response = self.promote()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["promotion"]["total_price"], 6000)
        client_for(self.owner).get(f"/api/v1/payments/{response.data['reference']}/")
        promotion = Promotion.objects.get()
        self.assertEqual(promotion.status, Promotion.IN_REVIEW)
        self.assertEqual(client_for(self.viewer).get("/api/v1/promotions/feed/").data, [])
        self.assertTrue(services.approve_promotion(promotion, self.staff))
        feed = client_for(self.viewer).get("/api/v1/promotions/feed/").data
        self.assertEqual([(p["id"], p["sponsored"]) for p in feed], [(self.post.pk, True)])
        self.assertEqual(client_for(self.owner).get("/api/v1/promotions/feed/").data, [])  # not your own
        self.assertEqual(APIClient().get("/api/v1/promotions/feed/").status_code, 200)
        for _ in range(2):
            client_for(self.viewer).post(f"/api/v1/promotions/{promotion.pk}/seen/")
        client_for(self.viewer).post(f"/api/v1/promotions/{promotion.pk}/click/")
        promotion.refresh_from_db()
        self.assertEqual((promotion.impressions, promotion.clicks), (1, 1))
        self.assertEqual(self.promote().status_code, 400)  # already running

    def test_ad_credit_pays_first_and_rejection_refunds_as_credit(self):
        services.add_entry(self.owner, LedgerEntry.AD_CREDIT, LedgerEntry.REFERRAL_REWARD, 10000)
        response = self.promote(days=3)
        self.assertIsNone(response.data["checkout_url"])
        self.assertEqual(services.balance(self.owner, LedgerEntry.AD_CREDIT), 1000)
        promotion = Promotion.objects.get()
        self.assertTrue(services.reject_promotion(promotion, self.staff, "Misleading"))
        self.assertEqual(services.balance(self.owner, LedgerEntry.AD_CREDIT), 10000)

    def test_unfinished_payment_returns_reserved_credit(self):
        services.add_entry(self.owner, LedgerEntry.AD_CREDIT, LedgerEntry.REFERRAL_REWARD, 1000)
        with using(FakeGateway(Verification("failed"))):
            promotion, _ = services.start_promotion(self.owner, self.post, 1)
            self.assertEqual(services.balance(self.owner, LedgerEntry.AD_CREDIT), 0)
            services.confirm_payment(promotion.payment)
        promotion.refresh_from_db()
        self.assertEqual(promotion.status, Promotion.CANCELLED)
        self.assertEqual(services.balance(self.owner, LedgerEntry.AD_CREDIT), 1000)

    def test_only_own_public_posts(self):
        private = Community.objects.create(name="Secret", description="x", visibility=Community.PRIVATE, created_by=self.owner)
        self.assertEqual(self.promote(post=Discussion.objects.create(author=self.owner, title="x", community=private)).status_code, 400)
        self.assertEqual(self.promote(post=Discussion.objects.create(author=self.viewer, title="theirs")).status_code, 404)
        self.assertEqual(self.promote(days=0).status_code, 400)

    @override_settings(PROMOTION_AUTO_APPROVE=True)
    def test_auto_approve(self):
        services.add_entry(self.owner, LedgerEntry.AD_CREDIT, LedgerEntry.REFERRAL_REWARD, 3000)
        self.promote(days=1)
        self.assertTrue(Promotion.objects.get().is_running)


@TEST_GATEWAY
class ReferralTests(TestCase):
    def test_inviter_earns_credit_when_invited_member_confirms_email(self):
        from apps.accounts.security import make_email_token

        inviter = make_user("inviter")
        client = APIClient()
        token = client.get("/api/v1/auth/csrf/").json()["csrfToken"]
        response = client.post("/api/v1/auth/register/", {
            "username": "newbie", "email": "newbie@example.com", "password": "Strong-pass-123",
            "password_confirm": "Strong-pass-123", "invited_by": "inviter",
        }, format="json", headers={"X-CSRFToken": token})
        self.assertEqual(response.status_code, 201, response.data)
        newbie = User.objects.get(username="newbie")
        self.assertEqual(Referral.objects.get().inviter, inviter)
        self.assertEqual(services.balance(inviter, LedgerEntry.AD_CREDIT), 0)

        verify = APIClient(enforce_csrf_checks=False)
        for _ in range(2):  # a second confirmation pays nothing more
            self.assertEqual(verify.post("/api/v1/auth/email/verify/", {"token": make_email_token(newbie)}, format="json").status_code, 200)
        self.assertEqual(services.balance(inviter, LedgerEntry.AD_CREDIT), 1000)
        data = client_for(inviter).get("/api/v1/money/referrals/").data
        self.assertEqual((data["joined"], data["confirmed"], data["credit_earned"]), (1, 1, 1000))
        self.assertTrue(data["invite_url"].endswith("/register?invite=inviter"))
        self.assertEqual(data["leaderboard"][0]["username"], "inviter")

    @override_settings(REFERRAL_MONTHLY_REWARD_LIMIT=1)
    def test_monthly_cap(self):
        inviter = make_user("inviter")
        for name in ("a", "b"):
            invited = make_user(name)
            services.record_referral(inviter, invited)
            services.reward_referral(invited)
        self.assertEqual(services.balance(inviter, LedgerEntry.AD_CREDIT), 1000)
