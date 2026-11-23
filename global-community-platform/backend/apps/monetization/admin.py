"""Staff tools: approve sponsored posts, send payouts, and see every payment."""
from django.contrib import admin, messages
from django.utils.html import format_html

from . import services
from .models import LedgerEntry, Payment, PayoutRequest, Promotion, Referral, Tip


class ReadOnlyAdmin(admin.ModelAdmin):
    """Money records change only through the app's own rules, never by hand-editing."""

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(ReadOnlyAdmin):
    list_display = ["reference", "purpose", "amount", "currency", "status", "provider", "payment_type", "payer", "created_at", "paid_at"]
    list_filter = ["status", "purpose", "provider"]
    search_fields = ["reference", "provider_transaction_id", "payer__username", "payer__email"]
    date_hierarchy = "created_at"
    actions = ["check_with_gateway"]

    @admin.action(description="Check the selected pending payments with the gateway")
    def check_with_gateway(self, request, queryset):
        for payment in queryset.filter(status=Payment.PENDING):
            services.confirm_payment(payment)
        self.message_user(request, "Checked. Paid ones are now fulfilled.")


@admin.register(Tip)
class TipAdmin(ReadOnlyAdmin):
    list_display = ["id", "sender", "recipient", "amount", "platform_fee", "status", "created_at"]
    list_filter = ["status"]
    search_fields = ["sender__username", "recipient__username"]
    date_hierarchy = "created_at"


@admin.register(LedgerEntry)
class LedgerEntryAdmin(ReadOnlyAdmin):
    list_display = ["user", "account", "kind", "amount", "description", "created_at"]
    list_filter = ["account", "kind"]
    search_fields = ["user__username", "description"]


@admin.register(PayoutRequest)
class PayoutRequestAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "amount", "network", "phone_number", "account_name", "status", "created_at", "processed_at"]
    list_filter = ["status", "network"]
    search_fields = ["user__username", "phone_number", "account_name"]
    readonly_fields = ["user", "amount", "network", "phone_number", "account_name", "status", "processed_by", "processed_at", "created_at"]
    fields = readonly_fields + ["note"]
    actions = ["mark_paid", "reject"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Mark as paid (after sending the money; put the receipt in Note first)")
    def mark_paid(self, request, queryset):
        done = sum(services.mark_payout_paid(p, request.user, p.note) for p in queryset)
        self.message_user(request, f"{done} payout(s) marked as paid.")

    @admin.action(description="Reject and return the money to their earnings (put the reason in Note first)")
    def reject(self, request, queryset):
        done = sum(services.reject_payout(p, request.user, p.note) for p in queryset)
        self.message_user(request, f"{done} payout(s) rejected and returned.", messages.WARNING)


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ["id", "post_link", "advertiser", "days", "total_price", "status", "starts_at", "ends_at", "impressions", "clicks"]
    list_filter = ["status"]
    search_fields = ["advertiser__username", "discussion__title", "discussion__body"]
    readonly_fields = ["advertiser", "discussion", "days", "daily_price", "total_price", "credit_used", "payment", "status", "starts_at", "ends_at", "impressions", "clicks", "reviewed_by", "created_at"]
    fields = readonly_fields + ["rejection_reason"]
    actions = ["approve", "reject"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Post")
    def post_link(self, obj):
        from django.conf import settings

        return format_html('<a href="{}/discussions/{}" target="_blank" rel="noopener">{}</a>', settings.FRONTEND_URL.rstrip("/"), obj.discussion_id, str(obj.discussion)[:60])

    @admin.action(description="Approve: start showing the selected sponsored posts")
    def approve(self, request, queryset):
        done = sum(services.approve_promotion(p, request.user) for p in queryset)
        self.message_user(request, f"{done} sponsored post(s) approved.")

    @admin.action(description="Reject and refund as ad credit (put the reason in Rejection reason first)")
    def reject(self, request, queryset):
        done = sum(services.reject_promotion(p, request.user, p.rejection_reason) for p in queryset)
        self.message_user(request, f"{done} sponsored post(s) rejected and refunded.", messages.WARNING)


@admin.register(Referral)
class ReferralAdmin(ReadOnlyAdmin):
    list_display = ["inviter", "invited", "created_at", "rewarded_at", "reward_amount"]
    search_fields = ["inviter__username", "invited__username"]
    list_filter = ["rewarded_at"]
