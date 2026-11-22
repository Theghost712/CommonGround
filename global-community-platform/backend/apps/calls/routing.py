from django.urls import re_path

from .consumers import CallsConsumer

websocket_urlpatterns = [re_path(r"^ws/calls/$", CallsConsumer.as_asgi())]
