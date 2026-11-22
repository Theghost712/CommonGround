from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from .models import ConnectionLabel, ContactMatch, Follow, FollowRequest

User = get_user_model()


def people_queryset():
    """Active users with follower/following counts, ready for PersonSerializer."""
    return (
        User.objects.filter(is_active=True)
        .select_related("profile")
        .annotate(
            followers_total=Count("follower_links", distinct=True),
            following_total=Count("following_links", distinct=True),
        )
    )


def relationship_map(viewer, user_ids):
    """How `viewer` is connected to each user id, computed in a fixed number of queries."""
    user_ids = list({int(pk) for pk in user_ids})
    if not user_ids or viewer is None or not viewer.is_authenticated:
        return {}
    from apps.safety.models import Block, Mute

    my_following = set(Follow.objects.filter(follower=viewer).values_list("following_id", flat=True))
    requested = set(FollowRequest.objects.filter(requester=viewer, target_id__in=user_ids).values_list("target_id", flat=True))
    private = set(User.objects.filter(pk__in=user_ids, profile__is_private=True).values_list("pk", flat=True))
    i_blocked = set(Block.objects.filter(blocker=viewer, blocked_id__in=user_ids).values_list("blocked_id", flat=True))
    muted = {row[0]: row[1:] for row in Mute.objects.filter(owner=viewer, muted_id__in=user_ids).values_list("muted_id", "mute_posts", "mute_stories")}
    follows_me = set(Follow.objects.filter(following=viewer, follower_id__in=user_ids).values_list("follower_id", flat=True))
    contacts = set(ContactMatch.objects.filter(owner=viewer, target_id__in=user_ids).values_list("target_id", flat=True))
    labels = dict(ConnectionLabel.objects.filter(owner=viewer, target_id__in=user_ids).values_list("target_id", "label"))

    # People I follow who also follow each user ("followed by amani and 3 others").
    mutual = defaultdict(list)
    if my_following:
        rows = (
            Follow.objects.filter(follower_id__in=my_following, following_id__in=user_ids)
            .exclude(follower=viewer)
            .select_related("follower")
            .order_by("-created_at")
        )
        for row in rows:
            mutual[row.following_id].append(row.follower.username)

    result = {}
    for pk in user_ids:
        is_following = pk in my_following
        follows_you = pk in follows_me
        result[pk] = {
            "is_self": pk == viewer.pk,
            "is_following": is_following,
            "follows_you": follows_you,
            "is_mutual": is_following and follows_you,
            "in_contacts": pk in contacts,
            "mutual_followers_count": len(mutual[pk]),
            "mutual_followers_preview": mutual[pk][:2],
            "label": labels.get(pk),
            "requested": pk in requested,
            "is_private": pk in private,
            # Can the viewer see this person's posts, stories and follower lists?
            "can_view": pk == viewer.pk or pk not in private or is_following,
            "blocked": pk in i_blocked,
            "muted_posts": bool(muted.get(pk, (False, False))[0]),
            "muted_stories": bool(muted.get(pk, (False, False))[1]),
        }
    return result


def approve_all_requests(user):
    """Approve every pending request to follow `user` (used when going public)."""
    pending = list(FollowRequest.objects.filter(target=user).values_list("requester_id", flat=True))
    Follow.objects.bulk_create([Follow(follower_id=pk, following=user) for pk in pending], ignore_conflicts=True)
    FollowRequest.objects.filter(target=user).delete()
    return len(pending)


def search_people(viewer, query):
    from apps.safety.services import blocked_user_ids

    terms = [term for term in query.split() if term]
    qs = people_queryset().exclude(pk=viewer.pk).exclude(pk__in=blocked_user_ids(viewer))
    for term in terms:
        qs = qs.filter(Q(username__icontains=term) | Q(first_name__icontains=term) | Q(last_name__icontains=term))
    return qs.order_by("-followers_total", "username")


def suggestions_for(viewer, limit=12):
    """People the viewer may know, each with the strongest reason we have."""
    from apps.communities.models import CommunityMembership

    from apps.safety.services import blocked_user_ids

    following = set(Follow.objects.filter(follower=viewer).values_list("following_id", flat=True))
    excluded = following | {viewer.pk} | blocked_user_ids(viewer)
    reasons = {}

    def add(user_id, reason, weight):
        if user_id in excluded:
            return
        current = reasons.get(user_id)
        if current is None or weight > current[1]:
            reasons[user_id] = (reason, weight)

    for target_id in ContactMatch.objects.filter(owner=viewer).values_list("target_id", flat=True):
        add(target_id, "In your contacts", 40)
    for follower_id in Follow.objects.filter(following=viewer).values_list("follower_id", flat=True):
        add(follower_id, "Follows you", 30)
    if following:
        friend_counts = (
            Follow.objects.filter(follower_id__in=following)
            .exclude(following_id__in=excluded)
            .values("following_id")
            .annotate(n=Count("follower_id"))
            .order_by("-n")[:50]
        )
        for row in friend_counts:
            n = row["n"]
            add(row["following_id"], f"Followed by {n} {'person' if n == 1 else 'people'} you follow", 20 + min(n, 9))
    my_communities = CommunityMembership.objects.filter(user=viewer, status=CommunityMembership.ACTIVE).values_list("community_id", flat=True)
    shared = (
        CommunityMembership.objects.filter(community_id__in=list(my_communities), status=CommunityMembership.ACTIVE)
        .exclude(user_id__in=excluded)
        .select_related("community")
        .order_by("-joined_at")[:100]
    )
    for membership in shared:
        add(membership.user_id, f"Also in {membership.community.name}", 10)

    ranked = sorted(reasons.items(), key=lambda item: -item[1][1])[:limit]
    users = {user.pk: user for user in people_queryset().filter(pk__in=[pk for pk, _ in ranked])}
    return [(users[pk], reason) for pk, (reason, _) in ranked if pk in users]
