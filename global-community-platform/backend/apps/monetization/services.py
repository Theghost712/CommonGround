"""Tips, sponsored posts, payouts and referral rewards.

Payments are confirmed by asking the gateway (`confirm_payment`), from the page the
payer returns to, from the gateway's webhook, or from the periodic job. All three can
race, so fulfilment locks the payment row and does its work exactly once.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .gateway import GatewayError, get_gateway
from .models import LedgerEntry, Payment, PayoutRequest, Promotion, Referral, Tip

logger = logging.getLogger(__name__)


def currency():
    return settings.MONETIZATION_CURRENCY


def money(amount):
    return f"{currency()} {amount:,}"


# Balances ----------------------------------------------------------------------------

def balance(user, account):
    return LedgerEntry.objects.filter(user=user, account=account).aggregate(total=Coalesce(Sum("amount"), 0))["total"]


def add_entry(user, account, kind, amount, description=""):
    return LedgerEntry.objects.create(user=user, account=account, kind=kind, amount=amount, description=description[:200])


def _lock_user(user):
    """Serialise balance changes for one member (two payouts at once can't both pass)."""
    from django.contrib.auth import get_user_model

    get_user_model().objects.select_for_update().filter(pk=user.pk).first()


# Checkout ----------------------------------------------------------------------------

def return_url():
    return f"{settings.FRONTEND_URL.rstrip('/')}/pay/return"


def _start_checkout(payment, user, title):
    gateway = get_gateway()
    payment.provider = gateway.name
    try:
        payment.checkout_url = gateway.checkout(payment, user, return_url(), title)
    except GatewayError as error:
        payment.status = Payment.FAILED
        payment.failure_reason = str(error)[:300]
        payment.save(update_fields=["provider", "status", "failure_reason"])
        _payment_failed(payment)
        raise ValidationError({"detail": str(error)})
    payment.save(update_fields=["provider", "checkout_url"])
    return payment.checkout_url


def _new_payment(user, purpose, amount):
    gateway = get_gateway()  # raises PaymentsUnavailable before anything is saved
    return Payment.objects.create(payer=user, purpose=purpose, amount=amount, currency=currency(), provider=gateway.name)


# Tips --------------------------------------------------------------------------------

def tip_fee(amount):
    return amount * settings.TIP_PLATFORM_FEE_PERCENT // 100


def start_tip(sender, recipient, amount, message="", discussion=None):
    from apps.safety.services import blocked_user_ids

    if recipient.pk == sender.pk:
        raise ValidationError({"detail": "You can't tip yourself."})
    if not recipient.is_active:
        raise ValidationError({"detail": "This account can't receive tips."})
    if recipient.pk in set(blocked_user_ids(sender)):
        raise ValidationError({"detail": "You can't tip this person."})
    if not settings.TIP_MIN_AMOUNT <= amount <= settings.TIP_MAX_AMOUNT:
        raise ValidationError({"amount": f"Tips are from {money(settings.TIP_MIN_AMOUNT)} to {money(settings.TIP_MAX_AMOUNT)}."})
    with transaction.atomic():
        payment = _new_payment(sender, Payment.TIP, amount)
        tip = Tip.objects.create(
            sender=sender, recipient=recipient, discussion=discussion, payment=payment,
            amount=amount, platform_fee=tip_fee(amount), message=message.strip()[:200],
        )
    name = recipient.get_full_name() or recipient.username
    return tip, _start_checkout(payment, sender, f"Tip for {name}")


def _fulfil_tip(tip):
    if tip.status == Tip.PAID:
        return
    tip.status = Tip.PAID
    tip.save(update_fields=["status"])
    sender_name = (tip.sender.get_full_name() or tip.sender.username) if tip.sender else "Someone"
    add_entry(tip.recipient, LedgerEntry.EARNINGS, LedgerEntry.TIP_RECEIVED, tip.creator_amount, f"Tip from {sender_name}")
    transaction.on_commit(lambda: _notify_tip(tip.pk))


def _notify_tip(tip_id):
    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    tip = Tip.objects.select_related("sender", "recipient").get(pk=tip_id)
    name = (tip.sender.get_full_name() or tip.sender.username) if tip.sender else "Someone"
    body = f"“{tip.message}” · " if tip.message else ""
    create_notification(
        tip.recipient, Notification.SYSTEM, f"{name} sent you a tip of {money(tip.amount)}",
        f"{body}{money(tip.creator_amount)} was added to your earnings.",
        target_url="/earnings", actor=tip.sender, data={"tip": tip.pk},
    )


# Sponsored posts ---------------------------------------------------------------------

def promotable(discussion, user):
    """A member can promote their own post if anyone, signed in or not, may see it."""
    from apps.discussions.views import visible_discussions

    return discussion.author_id == user.pk and visible_discussions(None).filter(pk=discussion.pk).exists()


def promotion_quote(user, days):
    if not 1 <= days <= settings.PROMOTION_MAX_DAYS:
        raise ValidationError({"days": f"Choose 1 to {settings.PROMOTION_MAX_DAYS} days."})
    total = settings.PROMOTION_DAILY_PRICE * days
    credit = min(total, max(0, balance(user, LedgerEntry.AD_CREDIT)))
    return {"days": days, "daily_price": settings.PROMOTION_DAILY_PRICE, "total": total, "credit_used": credit, "amount_due": total - credit}


def start_promotion(user, discussion, days):
    """Returns (promotion, checkout_url). The URL is None when ad credit covered it all."""
    if not promotable(discussion, user):
        raise ValidationError({"detail": "You can promote your own posts that are public (not in private or restricted communities, and not from a private account)."})
    in_progress = Q(status=Promotion.IN_REVIEW) | Q(status=Promotion.ACTIVE, ends_at__gt=timezone.now())
    if Promotion.objects.filter(in_progress, discussion=discussion).exists():
        raise ValidationError({"detail": "This post is already being promoted."})
    with transaction.atomic():
        _lock_user(user)
        quote = promotion_quote(user, days)
        promotion = Promotion.objects.create(
            advertiser=user, discussion=discussion, days=days, daily_price=quote["daily_price"],
            total_price=quote["total"], credit_used=quote["credit_used"],
        )
        if quote["credit_used"]:
            add_entry(user, LedgerEntry.AD_CREDIT, LedgerEntry.PROMOTION_SPEND, -quote["credit_used"], f"Sponsored post #{discussion.pk}")
        if quote["amount_due"] == 0:
            _promotion_paid(promotion)
            return promotion, None
        payment = _new_payment(user, Payment.PROMOTION, quote["amount_due"])
        promotion.payment = payment
        promotion.save(update_fields=["payment"])
    return promotion, _start_checkout(payment, user, f"Sponsored post for {days} day{'s' if days != 1 else ''}")


def _promotion_paid(promotion):
    if promotion.status != Promotion.AWAITING_PAYMENT:
        return
    promotion.status = Promotion.IN_REVIEW
    promotion.save(update_fields=["status"])
    if settings.PROMOTION_AUTO_APPROVE:
        approve_promotion(promotion, reviewer=None)


def approve_promotion(promotion, reviewer):
    if promotion.status != Promotion.IN_REVIEW:
        return False
    now = timezone.now()
    promotion.status = Promotion.ACTIVE
    promotion.starts_at = now
    promotion.ends_at = now + timedelta(days=promotion.days)
    promotion.reviewed_by = reviewer
    promotion.save(update_fields=["status", "starts_at", "ends_at", "reviewed_by"])
    _notify_advertiser(promotion, "Your sponsored post is live", f"It runs until {promotion.ends_at:%d %b %Y}.")
    return True


def reject_promotion(promotion, reviewer, reason):
    """Rejected promotions are refunded in full as ad credit (usable for another post)."""
    with transaction.atomic():
        promotion = Promotion.objects.select_for_update().get(pk=promotion.pk)
        if promotion.status != Promotion.IN_REVIEW:
            return False
        promotion.status = Promotion.REJECTED
        promotion.rejection_reason = reason[:300]
        promotion.reviewed_by = reviewer
        promotion.save(update_fields=["status", "rejection_reason", "reviewed_by"])
        add_entry(promotion.advertiser, LedgerEntry.AD_CREDIT, LedgerEntry.PROMOTION_REFUND, promotion.total_price, f"Refund: sponsored post #{promotion.discussion_id}")
    _notify_advertiser(
        promotion, "Your sponsored post was not approved",
        f"{reason or 'It did not meet our advertising rules.'} {money(promotion.total_price)} was returned to you as ad credit.",
    )
    return True


def _notify_advertiser(promotion, title, body):
    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    transaction.on_commit(lambda: create_notification(
        promotion.advertiser, Notification.SYSTEM, title, body, target_url="/earnings", data={"promotion": promotion.pk},
    ))


def running_promotions():
    now = timezone.now()
    return Promotion.objects.filter(status=Promotion.ACTIVE, starts_at__lte=now, ends_at__gt=now)


def sponsored_for(user, limit=3):
    """Sponsored posts to show `user`, chosen at random, never their own or hidden ones."""
    from apps.discussions.views import visible_discussions

    promotions = running_promotions()
    if user is not None and user.is_authenticated:
        promotions = promotions.exclude(advertiser=user)
        from apps.safety.services import muted_post_authors

        muted = muted_post_authors(user)
        if muted:
            promotions = promotions.exclude(advertiser_id__in=muted)
    visible = visible_discussions(user).values("pk")
    return list(promotions.filter(discussion_id__in=visible).order_by("?")[:limit])


# Payment confirmation ----------------------------------------------------------------

def confirm_payment(payment):
    """Ask the gateway how the payment went and act on it. Safe to call repeatedly."""
    if payment.status != Payment.PENDING:
        return payment
    try:
        verification = get_gateway().verify(payment)
    except GatewayError:
        return payment
    if verification.status == "pending":
        return payment
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status != Payment.PENDING:
            return payment
        payment.provider_transaction_id = verification.transaction_id[:64]
        payment.payment_type = verification.payment_type
        if verification.status == "successful" and verification.amount >= payment.amount and verification.currency == payment.currency:
            payment.status = Payment.SUCCESSFUL
            payment.paid_at = timezone.now()
            payment.save(update_fields=["status", "paid_at", "provider_transaction_id", "payment_type"])
            _payment_succeeded(payment)
        else:
            payment.status = Payment.FAILED
            if verification.status == "successful":
                logger.error("Payment %s: paid %s %s but %s %s was due", payment.reference, verification.amount, verification.currency, payment.amount, payment.currency)
                payment.failure_reason = "The amount paid did not match. Contact support."
            else:
                payment.failure_reason = verification.reason or "The payment was not completed."
            payment.save(update_fields=["status", "failure_reason", "provider_transaction_id", "payment_type"])
            _payment_failed(payment)
    return payment


def _payment_succeeded(payment):
    if payment.purpose == Payment.TIP:
        _fulfil_tip(Tip.objects.select_for_update().select_related("sender", "recipient").get(payment=payment))
    elif payment.purpose == Payment.PROMOTION:
        _promotion_paid(Promotion.objects.select_for_update().get(payment=payment))


def _payment_failed(payment):
    if payment.purpose == Payment.TIP:
        Tip.objects.filter(payment=payment, status=Tip.PENDING).update(status=Tip.FAILED)
    elif payment.purpose == Payment.PROMOTION:
        promotion = Promotion.objects.filter(payment=payment, status=Promotion.AWAITING_PAYMENT).first()
        if promotion:
            promotion.status = Promotion.CANCELLED
            promotion.save(update_fields=["status"])
            if promotion.credit_used:  # give back the credit it had reserved
                add_entry(promotion.advertiser, LedgerEntry.AD_CREDIT, LedgerEntry.PROMOTION_REFUND, promotion.credit_used, f"Unused: sponsored post #{promotion.discussion_id}")


def check_pending_payments():
    """Periodic job: settle payments whose webhook never arrived; give up after a day."""
    now = timezone.now()
    for payment in Payment.objects.filter(status=Payment.PENDING, created_at__gte=now - timedelta(days=2), created_at__lte=now - timedelta(minutes=2))[:100]:
        confirm_payment(payment)
    for payment in Payment.objects.filter(status=Payment.PENDING, created_at__lt=now - timedelta(days=1))[:100]:
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if payment.status == Payment.PENDING:
                payment.status = Payment.FAILED
                payment.failure_reason = "The payment was not completed in time."
                payment.save(update_fields=["status", "failure_reason"])
                _payment_failed(payment)


# Payouts -----------------------------------------------------------------------------

def request_payout(user, amount, network, phone_number, account_name):
    profile = getattr(user, "profile", None)
    if profile is None or profile.email_verified_at is None:
        raise ValidationError({"detail": "Confirm your email address before asking for a payout."})
    if amount < settings.PAYOUT_MIN_AMOUNT:
        raise ValidationError({"amount": f"The smallest payout is {money(settings.PAYOUT_MIN_AMOUNT)}."})
    with transaction.atomic():
        _lock_user(user)
        if PayoutRequest.objects.filter(user=user, status=PayoutRequest.REQUESTED).exists():
            raise ValidationError({"detail": "You already have a payout waiting. You can ask again once it's paid."})
        available = balance(user, LedgerEntry.EARNINGS)
        if amount > available:
            raise ValidationError({"amount": f"You have {money(available)} available."})
        payout = PayoutRequest.objects.create(user=user, amount=amount, network=network, phone_number=phone_number, account_name=account_name)
        add_entry(user, LedgerEntry.EARNINGS, LedgerEntry.PAYOUT, -amount, f"Payout to {payout.get_network_display()} {phone_number[-4:].rjust(len(phone_number), '•')}")
    return payout


def mark_payout_paid(payout, staff, note=""):
    with transaction.atomic():
        payout = PayoutRequest.objects.select_for_update().get(pk=payout.pk)
        if payout.status != PayoutRequest.REQUESTED:
            return False
        payout.status = PayoutRequest.PAID
        payout.processed_by, payout.processed_at, payout.note = staff, timezone.now(), note[:300]
        payout.save(update_fields=["status", "processed_by", "processed_at", "note"])
    _notify_payout(payout, f"{money(payout.amount)} was sent to your {payout.get_network_display()}")
    return True


def reject_payout(payout, staff, note=""):
    with transaction.atomic():
        payout = PayoutRequest.objects.select_for_update().get(pk=payout.pk)
        if payout.status != PayoutRequest.REQUESTED:
            return False
        payout.status = PayoutRequest.REJECTED
        payout.processed_by, payout.processed_at, payout.note = staff, timezone.now(), note[:300]
        payout.save(update_fields=["status", "processed_by", "processed_at", "note"])
        add_entry(payout.user, LedgerEntry.EARNINGS, LedgerEntry.PAYOUT_RETURNED, payout.amount, "Payout returned to your earnings")
    _notify_payout(payout, "Your payout could not be sent", note)
    return True


def _notify_payout(payout, title, body=""):
    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    transaction.on_commit(lambda: create_notification(payout.user, Notification.SYSTEM, title, body or payout.note, target_url="/earnings", data={"payout": payout.pk}))


# Referrals ---------------------------------------------------------------------------

def record_referral(inviter, invited):
    if inviter.pk != invited.pk:
        Referral.objects.get_or_create(invited=invited, defaults={"inviter": inviter})


def reward_referral(invited):
    """The invited member confirmed their email: credit the inviter (once, within a monthly cap)."""
    amount = settings.REFERRAL_REWARD_AMOUNT
    if amount <= 0:
        return None
    with transaction.atomic():
        referral = Referral.objects.select_for_update().select_related("inviter").filter(invited=invited, rewarded_at__isnull=True).first()
        if referral is None or not referral.inviter.is_active:
            return None
        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if Referral.objects.filter(inviter=referral.inviter, rewarded_at__gte=month_start).count() >= settings.REFERRAL_MONTHLY_REWARD_LIMIT:
            return None
        referral.rewarded_at = timezone.now()
        referral.reward_amount = amount
        referral.save(update_fields=["rewarded_at", "reward_amount"])
        name = invited.get_full_name() or invited.username
        add_entry(referral.inviter, LedgerEntry.AD_CREDIT, LedgerEntry.REFERRAL_REWARD, amount, f"{name} joined from your invite")
        inviter = referral.inviter

    from apps.notifications.models import Notification
    from apps.notifications.services import create_notification

    transaction.on_commit(lambda: create_notification(
        inviter, Notification.SYSTEM, f"You earned {money(amount)} ad credit",
        f"{name} confirmed their account. Use your credit to promote a post.", target_url="/earnings", actor=invited,
    ))
    return referral


def referral_leaderboard(limit=10):
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = (
        Referral.objects.filter(rewarded_at__gte=month_start, inviter__is_active=True)
        .values("inviter__username", "inviter__first_name", "inviter__last_name")
        .annotate(joined=Count("pk")).order_by("-joined", "inviter__username")[:limit]
    )
    return [
        {"username": row["inviter__username"], "display_name": f"{row['inviter__first_name']} {row['inviter__last_name']}".strip() or row["inviter__username"], "joined": row["joined"]}
        for row in rows
    ]


def referral_stats(user):
    counts = Referral.objects.filter(inviter=user).aggregate(
        joined=Count("pk"), confirmed=Count("pk", filter=Q(rewarded_at__isnull=False)),
        credit_earned=Coalesce(Sum("reward_amount"), 0),
    )
    return counts
