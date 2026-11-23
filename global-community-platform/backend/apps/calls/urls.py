from django.urls import path

from . import group, views

urlpatterns = [
    path("calls/", views.StartCallView.as_view(), name="call_start"),
    path("calls/active/", views.ActiveCallView.as_view(), name="call_active"),
    path("calls/<int:pk>/accept/", views.AcceptCallView.as_view(), name="call_accept"),
    path("calls/<int:pk>/decline/", views.DeclineCallView.as_view(), name="call_decline"),
    path("calls/<int:pk>/end/", views.EndCallView.as_view(), name="call_end"),
    path("calls/group/", group.GroupCallStartView.as_view(), name="group_call_start"),
    path("calls/group/active/", group.GroupCallActiveView.as_view(), name="group_call_active"),
    path("calls/group/<int:pk>/leave/", group.GroupCallLeaveView.as_view(), name="group_call_leave"),
    path("calls/group/<int:pk>/heartbeat/", group.GroupCallHeartbeatView.as_view(), name="group_call_heartbeat"),
]
