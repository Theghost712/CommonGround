from django.urls import path

from . import views

urlpatterns = [
    path("calls/", views.StartCallView.as_view(), name="call_start"),
    path("calls/active/", views.ActiveCallView.as_view(), name="call_active"),
    path("calls/<int:pk>/accept/", views.AcceptCallView.as_view(), name="call_accept"),
    path("calls/<int:pk>/decline/", views.DeclineCallView.as_view(), name="call_decline"),
    path("calls/<int:pk>/end/", views.EndCallView.as_view(), name="call_end"),
]
