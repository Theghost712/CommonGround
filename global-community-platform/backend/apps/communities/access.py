from django.db.models import Q

from .models import Community


def approved_community_content_q(community_lookup):
    """Match standalone content or content belonging to an approved community."""
    return Q(**{f"{community_lookup}__isnull": True}) | Q(
        **{f"{community_lookup}__approval_status": Community.APPROVED}
    )


def community_is_unused(community):
    """Only metadata and the creator's owner membership may exist at deletion time."""
    return not (
        community.discussions.exists()
        or community.events.exists()
        or community.announcements.exists()
        or community.rules.exists()
        or community.memberships.exclude(user_id=community.created_by_id).exists()
    )
