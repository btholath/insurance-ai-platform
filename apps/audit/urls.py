from django.urls import path

from .views import AuditHistoryView, AuditListView

urlpatterns = [
    path("", AuditListView.as_view(), name="audit-list"),
    path("history/<str:target_type>/<str:target_id>/", AuditHistoryView.as_view(), name="audit-history"),
]
