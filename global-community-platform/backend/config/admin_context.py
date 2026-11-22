from django.contrib.auth import get_user_model
from django.urls import reverse


def admin_dashboard_stats(request):
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

    from apps.communities.models import Community, CommunityMembership
    from apps.discussions.models import Discussion

    stats = []

    def add_stat(label, value, hint, url, tone):
        stats.append({"label": label, "value": value, "hint": hint, "url": url, "tone": tone})

    if user.has_perm("auth.view_user") or user.has_perm("auth.change_user"):
        add_stat(
            "Registered members",
            get_user_model().objects.count(),
            "User accounts",
            reverse("admin:auth_user_changelist"),
            "purple",
        )

    if user.has_perm("communities.view_community") or user.has_perm("communities.change_community"):
        add_stat(
            "Communities",
            Community.objects.count(),
            "Across all visibility settings",
            reverse("admin:communities_community_changelist"),
            "blue",
        )

    if user.has_perm("communities.change_community"):
        add_stat(
            "Awaiting review",
            Community.objects.filter(approval_status=Community.PENDING).count(),
            "Communities pending approval",
            f"{reverse('admin:communities_community_changelist')}?approval_status__exact={Community.PENDING}",
            "amber",
        )

    if user.has_perm("discussions.view_discussion") or user.has_perm("discussions.change_discussion"):
        add_stat(
            "Discussions",
            Discussion.objects.count(),
            "Community conversations",
            reverse("admin:discussions_discussion_changelist"),
            "blue",
        )

    if user.has_perm("communities.view_communitymembership") or user.has_perm("communities.change_communitymembership"):
        add_stat(
            "Active memberships",
            CommunityMembership.objects.filter(status=CommunityMembership.ACTIVE).count(),
            "People in approved spaces",
            reverse("admin:communities_communitymembership_changelist"),
            "blue",
        )

    return {"admin_dashboard_stats": stats}
