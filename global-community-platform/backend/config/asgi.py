import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.asgi import get_asgi_application

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

from apps.messaging.auth import JWTAuthMiddlewareStack
from apps.messaging.routing import websocket_urlpatterns as chat_routes
from apps.notifications.routing import websocket_urlpatterns as notification_routes
from apps.calls.routing import websocket_urlpatterns as call_routes

websocket_routes = chat_routes + notification_routes + call_routes

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        JWTAuthMiddlewareStack(
            URLRouter(websocket_routes)
        )
    ),
})
