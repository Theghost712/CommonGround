from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from channels.db import database_sync_to_async

from .models import UserPresence

User = get_user_model()


@database_sync_to_async
def user_connected(user_id):
    with transaction.atomic():
        User.objects.get(pk=user_id)

        presence, created = UserPresence.objects.get_or_create(
            user_id=user_id
        )

        presence = UserPresence.objects.select_for_update().get(
            pk=presence.pk
        )

        was_online = presence.active_connections > 0

        presence.active_connections += 1
        presence.is_online = True
        presence.save(update_fields=[
            "active_connections",
            "is_online",
            "updated_at",
        ])

        return not was_online


@database_sync_to_async
def user_disconnected(user_id):
    with transaction.atomic():
        try:
            presence = UserPresence.objects.select_for_update().get(
                user_id=user_id
            )
        except UserPresence.DoesNotExist:
            return False

        if presence.active_connections > 0:
            presence.active_connections -= 1

        if presence.active_connections == 0:
            presence.is_online = False
            presence.last_seen = timezone.now()
            presence.save(update_fields=[
                "active_connections",
                "is_online",
                "last_seen",
                "updated_at",
            ])
            return True

        presence.save(update_fields=[
            "active_connections",
            "updated_at",
        ])

        return False


@database_sync_to_async
def get_presence_snapshot():
    presences = (
        UserPresence.objects
        .select_related("user")
        .order_by("user__username")
    )

    return [
        {
            "user_id": presence.user_id,
            "username": presence.user.username,
            "status": "online" if presence.is_online else "offline",
            "last_seen": (
                presence.last_seen.isoformat()
                if presence.last_seen else None
            ),
        }
        for presence in presences
    ]
