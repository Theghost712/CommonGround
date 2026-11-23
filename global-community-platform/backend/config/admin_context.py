"""Data for the admin home page (only computed on that page, for staff)."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.timesince import timesince

DAYS = 14


def _url(name, query=""):
    try:
        return reverse(name) + query
    except NoReverseMatch:
        return ""


def _daily(queryset, field="created_at"):
    """Counts per day for the last DAYS days (oldest first), zero-filled."""
    today = timezone.localdate()
    start = today - timedelta(days=DAYS - 1)
    rows = (queryset.filter(**{f"{field}__date__gte": start}).annotate(day=TruncDate(field))
            .values("day").annotate(n=Count("pk")).values_list("day", "n"))
    counts = dict(rows)
    return [{"day": start + timedelta(days=i), "n": counts.get(start + timedelta(days=i), 0)} for i in range(DAYS)]


def _bars(series):
    """Heights in % for a small bar chart; the tallest bar is 100%."""
    peak = max((point["n"] for point in series), default=0) or 1
    return [{**point, "pct": max(4, round(point["n"] * 100 / peak)) if point["n"] else 0} for point in series]


def admin_dashboard_stats(request):
    user = getattr(request, "user", None)
    match = getattr(request, "resolver_match", None)
    if not match or match.namespace != "admin" or match.url_name != "index" or not user or not user.is_authenticated or not user.is_staff:
        return {"admin_dashboard_stats": [], "admin_dashboard": None}

    from apps.calls.models import Call, GroupCall
    from apps.communities.models import Community, CommunityMembership
    from apps.discussions.models import Discussion, DiscussionAttachment
    from apps.safety.models import Report

    User = get_user_model()
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    def can(*perms):
        return any(user.has_perm(perm) for perm in perms)

    def delta(this_week, last_week):
        """'+12 this week · 8 the week before' — counts, not percentages, which mislead on small numbers."""
        direction = "up" if this_week > last_week else "down" if this_week < last_week else "flat"
        return {"text": f"+{this_week} this week ({last_week} last week)", "dir": direction}

    # Needs attention ------------------------------------------------------
    attention = []
    if can("safety.view_report", "safety.change_report"):
        n = Report.objects.filter(status=Report.OPEN).count()
        attention.append({"label": "Open reports", "count": n, "hint": "Posts, comments or people reported by members",
                          "url": "/moderation", "action": "Review"})
    if can("communities.change_community"):
        n = Community.objects.filter(approval_status=Community.PENDING).count()
        attention.append({"label": "Communities awaiting approval", "count": n, "hint": "New communities stay hidden until approved",
                          "url": _url("admin:communities_community_changelist", f"?approval_status__exact={Community.PENDING}"), "action": "Approve"})
    if can("discussions.view_discussionattachment"):
        n = DiscussionAttachment.objects.filter(processing="failed").count()
        attention.append({"label": "Videos that couldn't be processed", "count": n, "hint": "Uploads that weren't playable videos",
                          "url": _url("admin:discussions_discussionattachment_changelist", "?processing__exact=failed"), "action": "Inspect"})
    open_items = sum(item["count"] for item in attention)

    # Key figures ----------------------------------------------------------
    kpis = []
    if can("auth.view_user", "auth.change_user"):
        users = User.objects.all()
        this, last = users.filter(date_joined__gte=week_ago).count(), users.filter(date_joined__gte=two_weeks_ago, date_joined__lt=week_ago).count()
        kpis.append({"label": "Members", "value": users.filter(is_active=True).count(), "delta": delta(this, last),
                     "url": _url("admin:auth_user_changelist"), "bars": _bars(_daily(users, "date_joined")), "unit": "sign-ups"})
    if can("discussions.view_discussion", "discussions.change_discussion"):
        posts = Discussion.objects.all()
        this, last = posts.filter(created_at__gte=week_ago).count(), posts.filter(created_at__gte=two_weeks_ago, created_at__lt=week_ago).count()
        kpis.append({"label": "Posts", "value": posts.count(), "delta": delta(this, last),
                     "url": _url("admin:discussions_discussion_changelist"), "bars": _bars(_daily(posts)), "unit": "posts"})
    if can("communities.view_community", "communities.change_community"):
        kpis.append({"label": "Communities", "value": Community.objects.count(),
                     "delta": {"text": f"{CommunityMembership.objects.filter(status=CommunityMembership.ACTIVE).count()} active memberships", "dir": "flat"},
                     "url": _url("admin:communities_community_changelist"), "bars": _bars(_daily(Community.objects.all())), "unit": "new communities"})
    if can("calls.view_call", "calls.view_groupcall"):
        live = Call.objects.filter(status__in=Call.LIVE).count() + GroupCall.objects.filter(status=GroupCall.LIVE).count()
        week = Call.objects.filter(created_at__gte=week_ago).count() + GroupCall.objects.filter(created_at__gte=week_ago).count()
        kpis.append({"label": "Calls this week", "value": week,
                     "delta": {"text": f"{live} live right now", "dir": "up" if live else "flat"},
                     "url": _url("admin:calls_call_changelist"), "bars": _bars(_daily(Call.objects.all())), "unit": "calls"})

    # Recent items ---------------------------------------------------------
    recent_reports = []
    if can("safety.view_report"):
        for report in Report.objects.filter(status=Report.OPEN).select_related("reporter", "target_owner")[:5]:
            recent_reports.append({
                "reason": report.get_reason_display(), "target": report.get_target_type_display(),
                "owner": report.target_owner.username if report.target_owner else "—", "by": report.reporter.username,
                "when": report.created_at, "ago": timesince(report.created_at, depth=1), "url": reverse("admin:safety_report_change", args=[report.pk]),
            })
    new_members = []
    if can("auth.view_user"):
        for member in User.objects.order_by("-date_joined")[:6]:
            new_members.append({"username": member.username, "name": member.get_full_name(), "joined": member.date_joined, "ago": timesince(member.date_joined, depth=1),
                                "staff": member.is_staff, "active": member.is_active,
                                "url": reverse("admin:auth_user_change", args=[member.pk])})

    usage = []
    if user.is_superuser:
        from apps.common.usage import usage_summary

        usage = usage_summary()
    dashboard = {
        "usage": usage,
        "today": timezone.localdate(),
        "attention": attention, "open_items": open_items,
        "kpis": kpis, "recent_reports": recent_reports, "new_members": new_members,
        "chart_days": DAYS,
    }
    # Kept for templates that still read the old key.
    legacy = [{"label": k["label"], "value": k["value"], "hint": k["delta"]["text"], "url": k["url"], "tone": "blue"} for k in kpis]
    return {"admin_dashboard_stats": legacy, "admin_dashboard": dashboard}
