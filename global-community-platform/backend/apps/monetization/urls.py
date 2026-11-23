from django.urls import path, re_path

from . import views

urlpatterns = [
    path("money/config/", views.MoneyConfigView.as_view(), name="money_config"),
    path("money/wallet/", views.WalletView.as_view(), name="money_wallet"),
    path("money/referrals/", views.ReferralView.as_view(), name="money_referrals"),
    path("tips/", views.TipCreateView.as_view(), name="tip_create"),
    path("promotions/", views.PromotionListCreateView.as_view(), name="promotions"),
    path("promotions/quote/", views.PromotionQuoteView.as_view(), name="promotion_quote"),
    path("promotions/feed/", views.SponsoredFeedView.as_view(), name="promotions_feed"),
    re_path(r"^promotions/(?P<pk>\d+)/(?P<event>seen|click)/$", views.PromotionEventView.as_view(), name="promotion_event"),
    re_path(r"^payments/(?P<reference>cg-[0-9a-f]{32})/$", views.PaymentStatusView.as_view(), name="payment_status"),
    path("payments/webhook/flutterwave/", views.flutterwave_webhook, name="flutterwave_webhook"),
]
