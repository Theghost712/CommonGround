from django.urls import path

from . import views

urlpatterns = [
    path("safety/blocks/", views.BlockView.as_view(), name="blocks"),
    path("safety/blocks/<str:username>/", views.BlockView.as_view(), name="block_user"),
    path("safety/mutes/", views.MuteView.as_view(), name="mutes"),
    path("safety/mutes/<str:username>/", views.MuteView.as_view(), name="mute_user"),
    path("safety/reports/", views.ReportView.as_view(), name="reports"),
]
