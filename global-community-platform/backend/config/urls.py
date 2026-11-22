from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from apps.events.views import CommunityEventViewSet

from apps.accounts.views import CurrentUserView, LoginView, LogoutView, RefreshView, RegisterView, UserProfileView, WebSocketTicketView, csrf_cookie
from apps.accounts.security_views import (
    EmailChangeView, EmailVerificationResendView, EmailVerifyView, PasswordChangeView,
    PasswordResetConfirmView, PasswordResetRequestView, SignOutEverywhereView,
)
from apps.communities.views import CommunityViewSet
from apps.discussions.polls import PollCreateView, PollVoteView
from apps.discussions.posts import DiscussionImageView, DiscussionVideoView, PostCreateView, VideoPostCreateView
from apps.discussions.views import CommentViewSet, DiscussionAttachmentDownloadView, DiscussionViewSet, HashtagDetailView, TrendingHashtagsView
from apps.messaging.views import ChatUserSearchView, ConversationViewSet
from apps.notifications.views import NotificationViewSet, NotificationPreferencesView

admin.site.site_header = "CommonGround Administration"
admin.site.site_title = "CommonGround Admin"
admin.site.index_title = "Platform overview"

router = DefaultRouter()
router.register("communities", CommunityViewSet, basename="community")
router.register("discussions", DiscussionViewSet, basename="discussion")
router.register("comments", CommentViewSet, basename="comment")
router.register("conversations", ConversationViewSet, basename="conversation")
router.register("notifications", NotificationViewSet, basename="notification")
router.register("events", CommunityEventViewSet, basename="event")

from apps.common.health import health

urlpatterns = [
    path("api/v1/health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("api/v1/auth/register/", RegisterView.as_view(), name="register"),
    path("api/v1/auth/csrf/", csrf_cookie, name="csrf_cookie"),
    path("api/v1/auth/token/", LoginView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/token/refresh/", RefreshView.as_view(), name="token_refresh"),
    path("api/v1/auth/logout/", LogoutView.as_view(), name="logout"),
    path("api/v1/auth/ws-ticket/", WebSocketTicketView.as_view(), name="websocket_ticket"),
    path("api/v1/auth/me/", CurrentUserView.as_view(), name="current_user"),
    path("api/v1/auth/profile/", UserProfileView.as_view(), name="user_profile"),
    path("api/v1/auth/password/reset/", PasswordResetRequestView.as_view(), name="password_reset"),
    path("api/v1/auth/password/reset/confirm/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("api/v1/auth/password/change/", PasswordChangeView.as_view(), name="password_change"),
    path("api/v1/auth/email/verify/", EmailVerifyView.as_view(), name="email_verify"),
    path("api/v1/auth/email/resend/", EmailVerificationResendView.as_view(), name="email_verify_resend"),
    path("api/v1/auth/email/change/", EmailChangeView.as_view(), name="email_change"),
    path("api/v1/auth/sessions/revoke/", SignOutEverywhereView.as_view(), name="sessions_revoke"),
    path("api/v1/attachments/<int:pk>/download/", DiscussionAttachmentDownloadView.as_view(), name="discussion_attachment_download"),
    path("api/v1/posts/", PostCreateView.as_view(), name="post_create"),
    path("api/v1/posts/video/", VideoPostCreateView.as_view(), name="video_post_create"),
    path("api/v1/posts/poll/", PollCreateView.as_view(), name="poll_post_create"),
    path("api/v1/discussions/<int:pk>/vote/", PollVoteView.as_view(), name="poll_vote"),
    path("api/v1/videos/<int:pk>/", DiscussionVideoView.as_view(), name="discussion_video"),
    path("api/v1/tags/trending/", TrendingHashtagsView.as_view(), name="tags_trending"),
    path("api/v1/tags/<str:name>/", HashtagDetailView.as_view(), name="tag_detail"),
    path("api/v1/images/<int:pk>/", DiscussionImageView.as_view(), name="discussion_image"),
    path("api/v1/messaging/users/", ChatUserSearchView.as_view(), name="chat_user_search"),
    path("api/v1/notifications/preferences/", NotificationPreferencesView.as_view(), name="notification_preferences"),
    path("api/v1/", include("apps.social.urls")),
    path("api/v1/", include("apps.stories.urls")),
    path("api/v1/", include("apps.safety.urls")),
    path("api/v1/", include("apps.moderation.urls")),
    path("api/v1/", include("apps.calls.urls")),
    path("api/v1/", include(router.urls)),
]
