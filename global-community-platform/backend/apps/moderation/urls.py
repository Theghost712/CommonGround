from django.urls import path

from . import views

urlpatterns = [
    path("moderation/queue/", views.QueueView.as_view(), name="moderation_queue"),
    path("moderation/decisions/", views.DecisionView.as_view(), name="moderation_decide"),
    path("moderation/log/", views.AuditLogView.as_view(), name="moderation_log"),
    path("moderation/accounts/<str:username>/", views.AccountRecordView.as_view(), name="moderation_account"),
    path("moderation/accounts/<str:username>/restore/", views.RestoreAccountView.as_view(), name="moderation_restore"),
]
