from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone


def admin_dashboard_stats(request):
    """Stat cards for the admin home page: what needs attention first, then totals."""
    user = getattr(request, "user", None)
    match = getattr(request, "resolver_match", None)
    if (
        not match
        or match.namespace != "admin"
        or match.url_name != "index"
        or not user
        or not user.is_authenticated
        or not user.is_staff
    ):
        return {"admin_dashboard_stats": []}

    from apps.calls.models import Call, GroupCall
    from apps.communities.models import Community, CommunityMembership
    from apps.discussions.models import Discussion, DiscussionAttachment
    from apps.safety.models import Report

    User = get_user_model()
    week_ago = timezone.now() - timedelta(days=7)
    stats = []

    def can(*perms):
        return any(user.has_perm(perm) for perm in perms)

    def add(label, value, hint, url, tone, urgent=False):
        stats.append({"label": label, "value": value, "hint": hint, "url": url, "tone": "red" if urgent and value else tone})

    # Needs attention
    if can("safety.view_report", "safety.change_report"):
        add("Open reports", Report.objects.filter(status=Report.OPEN).count(), "Waiting for a moderator",
            f"{reverse('admin:safety_report_changelist')}?status__exact={Report.OPEN}", "amber", urgent=True)
    if can("communities.change_community"):
        add("Awaiting review", Community.objects.filter(approval_status=Community.PENDING).count(), "Communities pending approval",
            f"{reverse('admin:communities_community_changelist')}?approval_status__exact={Community.PENDING}", "amber", urgent=True)
    if can("discussions.view_discussionattachment"):
        failed = DiscussionAttachment.objects.filter(processing="failed").count()
        pending = DiscussionAttachment.objects.filter(processing="pending").count()
        add("Videos", f"{pending} / {failed}", "Converting / couldn't be processed",
            f"{reverse('admin:discussions_discussionattachment_changelist')}?processing__exact=failed", "blue")

    # Activity
    if can("auth.view_user", "auth.change_user"):
        add("Members", User.objects.filter(is_active=True).count(),
            f"+{User.objects.filter(date_joined__gte=week_ago).count()} in the last 7 days",
            reverse("admin:auth_user_changelist"), "purple")
    if can("discussions.view_discussion", "discussions.change_discussion"):
        add("Posts", Discussion.objects.count(), f"+{Discussion.objects.filter(created_at__gte=week_ago).count()} in the last 7 days",
            reverse("admin:discussions_discussion_changelist"), "blue")
    if can("communities.view_community", "communities.change_community"):
        add("Communities", Community.objects.count(),
            f"{CommunityMembership.objects.filter(status=CommunityMembership.ACTIVE).count()} active memberships",
            reverse("admin:communities_community_changelist"), "blue")
    if can("calls.view_call", "calls.view_groupcall"):
        live = Call.objects.filter(status__in=Call.LIVE).count() + GroupCall.objects.filter(status=GroupCall.LIVE).count()
        add("Calls", live, f"Live now · {Call.objects.filter(created_at__gte=week_ago).count() + GroupCall.objects.filter(created_at__gte=week_ago).count()} in the last 7 days",
            reverse("admin:calls_call_changelist"), "green")

    return {"admin_dashboard_stats": stats}
