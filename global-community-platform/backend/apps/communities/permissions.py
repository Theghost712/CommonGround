from .models import Community, CommunityMembership


PLATFORM_COMMUNITY_PERMISSIONS = (
    "view_community",
    "change_community",
    "delete_community",
)


def has_platform_community_permission(user, permission=None):
    """Platform access is granted by Django permissions, never membership roles."""
    if not user or not user.is_authenticated or not user.is_staff:
        return False
    if user.is_superuser:
        return True
    if permission:
        return user.has_perm(f"communities.{permission}")
    return any(user.has_perm(f"communities.{name}") for name in PLATFORM_COMMUNITY_PERMISSIONS)


def has_community_role(user, community, roles, *, require_approved=True):
    if not user or not user.is_authenticated:
        return False
    if require_approved and community.approval_status != Community.APPROVED:
        return False
    return CommunityMembership.objects.filter(
        community=community,
        user=user,
        status=CommunityMembership.ACTIVE,
        role__in=roles,
    ).exists()
