import json
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.discussions.models import Discussion
from . import services
from .gateway import PaymentsUnavailable, get_gateway, payments_enabled
from .models import LedgerEntry, Payment, PayoutRequest, Promotion, Tip

logger = logging.getLogger(__name__)
User = get_user_model()


def _unavailable(error):
    return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class PaymentThrottleMixin:
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "payments"


class MoneyConfigView(APIView):
    """Prices and limits the app shows before anyone pays."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({
            "enabled": payments_enabled(),
            "test_mode": payments_enabled() and get_gateway().name == "test",
            "currency": settings.MONETIZATION_CURRENCY,
            "tip_min": settings.TIP_MIN_AMOUNT,
            "tip_max": settings.TIP_MAX_AMOUNT,
            "tip_fee_percent": settings.TIP_PLATFORM_FEE_PERCENT,
            "payout_min": settings.PAYOUT_MIN_AMOUNT,
            "promotion_daily_price": settings.PROMOTION_DAILY_PRICE,
            "promotion_max_days": settings.PROMOTION_MAX_DAYS,
            "referral_reward": settings.REFERRAL_REWARD_AMOUNT,
            "payout_networks": [{"value": value, "label": label} for value, label in PayoutRequest.NETWORK_CHOICES],
        })


class TipInput(serializers.Serializer):
    username = serializers.CharField(max_length=150, required=False, allow_blank=True)
    discussion = serializers.IntegerField(required=False, allow_null=True)
    amount = serializers.IntegerField(min_value=1)
    message = serializers.CharField(max_length=200, required=False, allow_blank=True)


class TipCreateView(PaymentThrottleMixin, APIView):
    """POST {username | discussion, amount, message?} → {checkout_url, reference}."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = TipInput(data=request.data)
        data.is_valid(raise_exception=True)
        discussion = None
        if data.validated_data.get("discussion"):
            from apps.discussions.views import visible_discussions

            discussion = get_object_or_404(visible_discussions(request.user).select_related("author"), pk=data.validated_data["discussion"])
            recipient = discussion.author
        else:
            recipient = get_object_or_404(User, username__iexact=data.validated_data.get("username", ""), is_active=True)
        try:
            tip, url = services.start_tip(request.user, recipient, data.validated_data["amount"], data.validated_data.get("message", ""), discussion)
        except PaymentsUnavailable as error:
            return _unavailable(error)
        return Response({"checkout_url": url, "reference": tip.payment.reference}, status=status.HTTP_201_CREATED)


class PromotionInput(serializers.Serializer):
    discussion = serializers.IntegerField()
    days = serializers.IntegerField(min_value=1)


class PromotionQuoteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            days = int(request.query_params.get("days", "1"))
        except ValueError:
            days = 0
        return Response(services.promotion_quote(request.user, days))


def promotion_data(promotion):
    return {
        "id": promotion.id, "discussion": promotion.discussion_id,
        "discussion_title": str(promotion.discussion)[:120],
        "days": promotion.days, "total_price": promotion.total_price, "credit_used": promotion.credit_used,
        "status": promotion.status, "status_label": promotion.get_status_display(),
        "rejection_reason": promotion.rejection_reason,
        "starts_at": promotion.starts_at, "ends_at": promotion.ends_at,
        "is_running": promotion.is_running, "impressions": promotion.impressions, "clicks": promotion.clicks,
        "created_at": promotion.created_at,
    }


class PromotionListCreateView(PaymentThrottleMixin, APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_throttles(self):
        return super().get_throttles() if self.request.method == "POST" else []

    def get(self, request):
        promotions = Promotion.objects.filter(advertiser=request.user).exclude(status=Promotion.CANCELLED).select_related("discussion")[:50]
        return Response([promotion_data(p) for p in promotions])

    def post(self, request):
        data = PromotionInput(data=request.data)
        data.is_valid(raise_exception=True)
        discussion = get_object_or_404(Discussion, pk=data.validated_data["discussion"], author=request.user)
        try:
            promotion, url = services.start_promotion(request.user, discussion, data.validated_data["days"])
        except PaymentsUnavailable as error:
            return _unavailable(error)
        return Response({
            "promotion": promotion_data(promotion), "checkout_url": url,
            "reference": promotion.payment.reference if promotion.payment else None,
        }, status=status.HTTP_201_CREATED)


class SponsoredFeedView(APIView):
    """GET → up to 3 sponsored posts for the viewer's feed, each with its promotion id."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from apps.discussions.polls import with_polls
        from apps.discussions.serializers import DiscussionSerializer
        from apps.discussions.views import with_stats

        promotions = services.sponsored_for(request.user)
        if not promotions:
            return Response([])
        by_discussion = {p.discussion_id: p.pk for p in promotions}
        posts = with_polls(with_stats(Discussion.objects.filter(pk__in=by_discussion), request.user), request.user) \
            .select_related("author", "author__profile", "community").prefetch_related("attachments")
        data = DiscussionSerializer(posts, many=True, context={"request": request}).data
        for item in data:
            item["sponsored"] = True
            item["promotion_id"] = by_discussion[item["id"]]
        return Response(data)


class PromotionEventView(APIView):
    """POST /promotions/<id>/<seen|click>/: counted once per viewer per day."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = []

    def post(self, request, pk, event):
        viewer = f"u{request.user.pk}" if request.user.is_authenticated else f"ip{request.META.get('REMOTE_ADDR', '')}"
        field = "impressions" if event == "seen" else "clicks"
        if cache.add(f"promo:{pk}:{field}:{viewer}", 1, timeout=86400):
            services.running_promotions().filter(pk=pk).update(**{field: F(field) + 1})
        return Response(status=status.HTTP_204_NO_CONTENT)


class PaymentStatusView(APIView):
    """GET /payments/<reference>/ → checks with the gateway, then reports the result."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, reference):
        payment = get_object_or_404(Payment, reference=reference, payer=request.user)
        payment = services.confirm_payment(payment)
        result = {"reference": payment.reference, "status": payment.status, "purpose": payment.purpose, "amount": payment.amount, "currency": payment.currency, "failure_reason": payment.failure_reason}
        if payment.purpose == Payment.TIP:
            tip = Tip.objects.select_related("recipient").get(payment=payment)
            result["recipient"] = tip.recipient.username
            result["discussion"] = tip.discussion_id
        elif payment.purpose == Payment.PROMOTION:
            promotion = Promotion.objects.get(payment=payment)
            result["promotion"] = promotion_data(promotion)
        return Response(result)


@csrf_exempt
@require_POST
def flutterwave_webhook(request):
    """Flutterwave calls this when a payment changes. We only use it as a hint to verify."""
    try:
        gateway = get_gateway()
    except PaymentsUnavailable:
        return HttpResponse(status=503)
    if not gateway.webhook_is_authentic(request):
        return HttpResponse(status=401)
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return HttpResponse(status=400)
    data = payload.get("data") or {}
    reference = data.get("tx_ref") or data.get("txRef") or payload.get("txRef") or ""
    payment = Payment.objects.filter(reference=str(reference)[:64]).first()
    if payment is not None:
        services.confirm_payment(payment)
    return HttpResponse(status=200)


class PayoutInput(serializers.Serializer):
    amount = serializers.IntegerField(min_value=1)
    network = serializers.ChoiceField(choices=PayoutRequest.NETWORK_CHOICES)
    phone_number = serializers.CharField(max_length=20)
    account_name = serializers.CharField(max_length=120)

    def validate_phone_number(self, value):
        from apps.accounts.phone import normalize_phone

        normalized = normalize_phone(value)
        if not normalized:
            raise serializers.ValidationError("Enter the mobile money number, e.g. 0712 345 678.")
        return normalized


class WalletView(PaymentThrottleMixin, APIView):
    """GET → balances, recent activity, tips, payouts. POST → ask for a payout."""

    permission_classes = [permissions.IsAuthenticated]

    def get_throttles(self):
        return super().get_throttles() if self.request.method == "POST" else []

    def get(self, request):
        user = request.user
        tips = Tip.objects.filter(recipient=user, status=Tip.PAID).select_related("sender")[:30]
        payouts = PayoutRequest.objects.filter(user=user)[:20]
        entries = LedgerEntry.objects.filter(user=user)[:50]
        return Response({
            "currency": settings.MONETIZATION_CURRENCY,
            "earnings": services.balance(user, LedgerEntry.EARNINGS),
            "ad_credit": services.balance(user, LedgerEntry.AD_CREDIT),
            "has_pending_payout": any(p.status == PayoutRequest.REQUESTED for p in payouts),
            "tips": [{
                "id": t.id, "amount": t.amount, "creator_amount": t.creator_amount, "message": t.message,
                "sender": t.sender.username if t.sender else None,
                "sender_name": (t.sender.get_full_name() or t.sender.username) if t.sender else "Deleted account",
                "discussion": t.discussion_id, "created_at": t.created_at,
            } for t in tips],
            "payouts": [{
                "id": p.id, "amount": p.amount, "network": p.get_network_display(), "phone_number": p.phone_number,
                "status": p.status, "status_label": p.get_status_display(), "note": p.note, "created_at": p.created_at,
            } for p in payouts],
            "activity": [{
                "id": e.id, "account": e.account, "kind": e.get_kind_display(), "amount": e.amount,
                "description": e.description, "created_at": e.created_at,
            } for e in entries],
        })

    def post(self, request):
        data = PayoutInput(data=request.data)
        data.is_valid(raise_exception=True)
        payout = services.request_payout(request.user, **data.validated_data)
        return Response({"id": payout.id, "status": payout.status}, status=status.HTTP_201_CREATED)


class ReferralView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        stats = services.referral_stats(request.user)
        return Response({
            "invite_url": f"{settings.FRONTEND_URL.rstrip('/')}/register?invite={request.user.username}",
            "reward": settings.REFERRAL_REWARD_AMOUNT,
            "currency": settings.MONETIZATION_CURRENCY,
            **stats,
            "leaderboard": services.referral_leaderboard(),
        })
