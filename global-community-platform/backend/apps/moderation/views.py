from collections import Counter, defaultdict

from django.contrib.auth import get_user_model
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserProfile
from apps.safety.models import Report

from .models import ModerationAction
from .services import (
    REASON_LABELS, ModerationError, apply_decision, can_moderate, describe, load_target,
    moderated_community_ids, reports_in_scope, restore_account,
)

User = get_user_model()
QUEUE_LIMIT = 50


class IsModerator(permissions.BasePermission):
    message = "Only moderators can open this."

    def has_permission(self, request, view):
        return can_moderate(request.user)


def person(user):
    if user is None:
        return None
    profile = UserProfile.objects.filter(user=user).values("suspended_until").first() or {}
    until = profile.get("suspended_until")
    return {
        "id": user.pk, "username": user.username, "display_name": user.get_full_name() or user.username,
        "is_active": user.is_active, "is_staff": user.is_staff,
        "suspended_until": until if until and until > timezone.now() else None,
    }


class QueueView(APIView):
    """Open reports grouped by the reported thing, most-reported first."""

    permission_classes = [permissions.IsAuthenticated, IsModerator]

    def get(self, request):
        scope = reports_in_scope(request.user).filter(status=Report.OPEN)
        groups = list(scope.values("target_type", "target_id").annotate(count=Count("pk"), latest=Max("created_at")).order_by("-count", "-latest")[:QUEUE_LIMIT])
        keys = {(g["target_type"], g["target_id"]) for g in groups}
        details = defaultdict(list)
        reasons = defaultdict(Counter)
        for report in scope.filter(target_id__in={k[1] for k in keys}).order_by("-created_at").values("target_type", "target_id", "reason", "details"):
            key = (report["target_type"], report["target_id"])
            if key not in keys:
                continue
            reasons[key][report["reason"]] += 1
            if report["details"] and len(details[key]) < 3:
                details[key].append(report["details"])
        mod_ids = set(moderated_community_ids(request.user))
        items = []
        for group in groups:
            key = (group["target_type"], group["target_id"])
            obj, owner, community = load_target(*key)
            items.append({
                "target_type": key[0], "target_id": key[1], "report_count": group["count"], "latest_at": group["latest"],
                "reasons": [{"reason": r, "label": REASON_LABELS.get(r, r), "count": n} for r, n in reasons[key].most_common()],
                "details": details[key],
                "owner": person(owner),
                "community": {"id": community.pk, "name": community.name} if community else None,
                "preview": describe(key[0], obj),
                "can_enforce": request.user.is_staff,  # warn / suspend / ban
                "is_community_scope": bool(community and community.pk in mod_ids),
            })
        return Response({"count": scope.values("target_type", "target_id").distinct().count(), "results": items})


class DecisionSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(choices=Report.TARGETS)
    target_id = serializers.IntegerField(min_value=1)
    action = serializers.ChoiceField(choices=[ModerationAction.DISMISS, ModerationAction.REMOVE, ModerationAction.WARN, ModerationAction.SUSPEND, ModerationAction.BAN])
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    days = serializers.IntegerField(required=False, min_value=1, max_value=365)
    remove_content = serializers.BooleanField(required=False, default=False)


class DecisionView(APIView):
    """POST {target_type, target_id, action, reason, days?, remove_content?}."""

    permission_classes = [permissions.IsAuthenticated, IsModerator]

    def post(self, request):
        data = DecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        try:
            log = apply_decision(request.user, values["target_type"], values["target_id"], values["action"],
                                 values["reason"], values.get("days"), values["remove_content"])
        except ModerationError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Done.", "action": log.action, "reports_closed": log.reports_closed}, status=status.HTTP_201_CREATED)


class RestoreAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsModerator]

    def post(self, request, username):
        user = get_object_or_404(User, username=username)
        try:
            restore_account(request.user, user, str(request.data.get("reason", "")))
        except ModerationError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": f"{user.username} can sign in again.", "user": person(user)})


class AccountRecordView(APIView):
    """A user's moderation record (staff): status, reports received, past actions."""

    permission_classes = [permissions.IsAuthenticated, IsModerator]

    def get(self, request, username):
        if not request.user.is_staff:
            raise PermissionDenied("Only site staff can see account records.")
        user = get_object_or_404(User, username=username)
        reports = Report.objects.filter(target_owner=user)
        history = ModerationAction.objects.filter(target_user=user).select_related("moderator")[:50]
        return Response({
            "user": person(user),
            "reports_received": reports.count(),
            "open_reports": reports.filter(status=Report.OPEN).count(),
            "history": [log_row(item) for item in history],
        })


def log_row(item):
    return {
        "id": item.id, "action": item.action, "action_label": item.get_action_display(),
        "moderator": item.moderator.username if item.moderator else None,
        "target_type": item.target_type, "target_id": item.target_id,
        "target_user": item.target_user.username if item.target_user else None,
        "community": item.community.name if item.community else None,
        "reason": item.reason, "snapshot": item.snapshot, "reports_closed": item.reports_closed,
        "suspended_until": item.suspended_until, "created_at": item.created_at,
    }


class AuditLogView(APIView):
    """Recent decisions: all for staff, their communities' for community moderators."""

    permission_classes = [permissions.IsAuthenticated, IsModerator]

    def get(self, request):
        actions = ModerationAction.objects.select_related("moderator", "target_user", "community")
        if not request.user.is_staff:
            actions = actions.filter(community_id__in=moderated_community_ids(request.user))
        username = request.query_params.get("user")
        if username:
            actions = actions.filter(target_user__username=username)
        return Response([log_row(item) for item in actions[:100]])
