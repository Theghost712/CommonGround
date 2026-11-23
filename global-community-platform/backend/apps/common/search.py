"""GET /api/v1/search/?q= — one search box for people, posts, hashtags and communities."""

from django.db.models import Count, Q
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView


class SearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def get(self, request):
        from apps.communities.models import Community
        from apps.discussions.models import Hashtag
        from apps.discussions.serializers import DiscussionSerializer
        from apps.discussions.views import visible_discussions, with_stats
        from apps.safety.services import blocked_user_ids
        from apps.social.serializers import PersonSerializer
        from apps.social.services import people_queryset, relationship_map

        q = str(request.query_params.get("q", "")).strip()[:80]
        if len(q.lstrip("#@")) < 2:
            return Response({"q": q, "people": [], "posts": [], "tags": [], "communities": []})
        term = q.lstrip("#@")
        blocked = blocked_user_ids(request.user)

        people = list(people_queryset().exclude(pk__in=blocked).filter(
            Q(username__icontains=term) | Q(first_name__icontains=term) | Q(last_name__icontains=term)
        ).order_by("-followers_total", "username")[:6]) if not q.startswith("#") else []
        relations = relationship_map(request.user, [p.pk for p in people])

        posts = []
        if not q.startswith("@"):
            found = with_stats(visible_discussions(request.user), request.user).filter(
                Q(title__icontains=term) | Q(body__icontains=term) | Q(hashtags__name=term.lower())
            ).select_related("author", "author__profile", "community").prefetch_related("attachments").distinct().order_by("-created_at")[:10]
            posts = DiscussionSerializer(found, many=True, context={"request": request}).data

        tags = list(Hashtag.objects.filter(name__icontains=term.lower()).annotate(n=Count("discussions")).filter(n__gt=0)
                    .order_by("-n", "name").values("name", "n")[:6]) if not q.startswith("@") else []

        communities = []
        if not q.startswith(("@", "#")):
            for c in Community.objects.filter(approval_status=Community.APPROVED).filter(Q(name__icontains=term) | Q(description__icontains=term)).exclude(
                    visibility="private").annotate(members=Count("memberships", filter=Q(memberships__status="active"))).order_by("-members")[:5]:
                communities.append({"id": c.pk, "name": c.name, "slug": getattr(c, "slug", ""), "members": c.members, "category": c.category,
                                    "description": (c.description or "")[:140]})

        return Response({
            "q": q,
            "people": PersonSerializer(people, many=True, context={"relations": relations}).data,
            "posts": posts,
            "tags": [{"name": t["name"], "count": t["n"]} for t in tags],
            "communities": communities,
        })
