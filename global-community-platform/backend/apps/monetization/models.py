"""Money on CommonGround: tips to creators, sponsored posts and referral rewards.

Amounts are whole units of MONETIZATION_CURRENCY (Tanzanian shillings by default,
which have no cents in practice), stored as integers so sums are exact.

Every change to someone's balance is a LedgerEntry. A balance is the sum of its
entries, so it can always be explained line by line and is never edited in place.
"""
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Payment(models.Model):
    """One checkout with the payment gateway (mobile money or card)."""

    TIP = "tip"
    PROMOTION = "promotion"
    PURPOSE_CHOICES = [(TIP, "Tip"), (PROMOTION, "Sponsored post")]

    PENDING = "pending"
    SUCCESSFUL = "successful"
    FAILED = "failed"
    STATUS_CHOICES = [(PENDING, "Waiting for payment"), (SUCCESSFUL, "Paid"), (FAILED, "Failed or cancelled")]

    # Our reference, sent to the gateway as tx_ref. Unguessable so it can sit in URLs.
    reference = models.CharField(max_length=64, unique=True, default="", editable=False)
    payer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="payments")
    purpose = models.CharField(max_length=12, choices=PURPOSE_CHOICES)
    amount = models.PositiveIntegerField()
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    provider = models.CharField(max_length=20)
    provider_transaction_id = models.CharField(max_length=64, blank=True)
    payment_type = models.CharField(max_length=40, blank=True, help_text="e.g. mobilemoneytz, card")
    checkout_url = models.URLField(max_length=1000, blank=True)
    failure_reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"cg-{uuid.uuid4().hex}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_purpose_display()} {self.amount} {self.currency} ({self.status})"


class LedgerEntry(models.Model):
    """A signed change to one of a member's two balances.

    earnings: money from tips, which can be paid out to mobile money.
    ad_credit: credit for sponsored posts (referral rewards, refunds). Not withdrawable.
    """

    EARNINGS = "earnings"
    AD_CREDIT = "ad_credit"
    ACCOUNT_CHOICES = [(EARNINGS, "Earnings"), (AD_CREDIT, "Ad credit")]

    TIP_RECEIVED = "tip_received"
    PAYOUT = "payout"
    PAYOUT_RETURNED = "payout_returned"
    REFERRAL_REWARD = "referral_reward"
    PROMOTION_SPEND = "promotion_spend"
    PROMOTION_REFUND = "promotion_refund"
    ADJUSTMENT = "adjustment"
    KIND_CHOICES = [
        (TIP_RECEIVED, "Tip received"),
        (PAYOUT, "Payout to mobile money"),
        (PAYOUT_RETURNED, "Payout returned"),
        (REFERRAL_REWARD, "Referral reward"),
        (PROMOTION_SPEND, "Sponsored post"),
        (PROMOTION_REFUND, "Sponsored post refund"),
        (ADJUSTMENT, "Adjustment by staff"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ledger_entries")
    account = models.CharField(max_length=10, choices=ACCOUNT_CHOICES)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    amount = models.IntegerField(help_text="Positive adds to the balance, negative takes from it.")
    description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "account"])]
        verbose_name_plural = "ledger entries"

    def __str__(self):
        return f"{self.user} {self.account} {self.amount:+d} ({self.kind})"


class Tip(models.Model):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    STATUS_CHOICES = [(PENDING, "Waiting for payment"), (PAID, "Paid"), (FAILED, "Failed")]

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="tips_sent")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tips_received")
    discussion = models.ForeignKey("discussions.Discussion", on_delete=models.SET_NULL, null=True, blank=True, related_name="tips")
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name="tip")
    amount = models.PositiveIntegerField()
    platform_fee = models.PositiveIntegerField(default=0)
    message = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "status", "-created_at"])]

    @property
    def creator_amount(self):
        return self.amount - self.platform_fee

    def __str__(self):
        return f"Tip {self.amount} to {self.recipient}"


class PayoutRequest(models.Model):
    """A creator asks for their earnings on mobile money. Staff send it and mark it paid."""

    REQUESTED = "requested"
    PAID = "paid"
    REJECTED = "rejected"
    STATUS_CHOICES = [(REQUESTED, "Requested"), (PAID, "Paid"), (REJECTED, "Rejected")]

    NETWORK_CHOICES = [
        ("mpesa", "M-Pesa (Vodacom)"),
        ("tigopesa", "Mixx by Yas (Tigo Pesa)"),
        ("airtelmoney", "Airtel Money"),
        ("halopesa", "HaloPesa"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payout_requests")
    amount = models.PositiveIntegerField()
    network = models.CharField(max_length=12, choices=NETWORK_CHOICES)
    phone_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=120)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=REQUESTED, db_index=True)
    note = models.CharField(max_length=300, blank=True, help_text="Shown to the member, e.g. the transfer receipt or why it was rejected.")
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payout {self.amount} to {self.user} ({self.status})"


class Promotion(models.Model):
    """A sponsored post: shown in other members' feeds, labelled "Sponsored"."""

    AWAITING_PAYMENT = "awaiting_payment"
    IN_REVIEW = "in_review"
    ACTIVE = "active"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (AWAITING_PAYMENT, "Waiting for payment"),
        (IN_REVIEW, "Waiting for review"),
        (ACTIVE, "Approved"),
        (REJECTED, "Rejected"),
        (CANCELLED, "Payment not completed"),
    ]

    advertiser = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="promotions")
    discussion = models.ForeignKey("discussions.Discussion", on_delete=models.CASCADE, related_name="promotions")
    days = models.PositiveSmallIntegerField()
    daily_price = models.PositiveIntegerField()
    total_price = models.PositiveIntegerField()
    credit_used = models.PositiveIntegerField(default=0)
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, null=True, blank=True, related_name="promotion")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=AWAITING_PAYMENT, db_index=True)
    rejection_reason = models.CharField(max_length=300, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True, db_index=True)
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def amount_due(self):
        return self.total_price - self.credit_used

    @property
    def is_running(self):
        now = timezone.now()
        return self.status == self.ACTIVE and self.starts_at is not None and self.starts_at <= now < self.ends_at

    def __str__(self):
        return f"Sponsored post {self.discussion_id} for {self.days} days ({self.status})"


class Referral(models.Model):
    """Someone joined through a member's invite link."""

    inviter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referrals_made")
    invited = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="referred_by")
    # Set once the new member confirms their email and the inviter is credited.
    rewarded_at = models.DateTimeField(null=True, blank=True, db_index=True)
    reward_amount = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["inviter", "-created_at"])]

    def __str__(self):
        return f"{self.inviter} invited {self.invited}"
