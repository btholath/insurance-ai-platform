from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.permissions import HasRole

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditPagination(PageNumberPagination):
    page_size = 50


class AuditListView(ListAPIView):
    serializer_class = AuditLogSerializer
    permission_classes = [HasRole(Role.COMPLIANCE_OFFICER, Role.SYSTEM_ADMINISTRATOR)]
    pagination_class = AuditPagination

    def get_queryset(self):
        queryset = AuditLog.objects.all()

        target_type = self.request.query_params.get("target_type")
        if target_type:
            queryset = queryset.filter(target_type=target_type)

        target_id = self.request.query_params.get("target_id")
        if target_id:
            queryset = queryset.filter(target_id=target_id)

        actor = self.request.query_params.get("actor")
        if actor:
            queryset = queryset.filter(actor_id=actor)

        action = self.request.query_params.get("action")
        if action:
            queryset = queryset.filter(action=action)

        ordering = self.request.query_params.get("ordering")
        if ordering == "timestamp":
            queryset = queryset.order_by("timestamp", "id")
        else:
            queryset = queryset.order_by("-timestamp", "-id")

        return queryset


class AuditHistoryView(APIView):
    # Route type is "detail" (addresses one target record's history), so
    # HasRole's has_permission() must defer to has_object_permission() for
    # the 404-not-403 existence-non-disclosure rule (FR-012) to apply. This
    # view has no single model instance to look up (the queryset can
    # legitimately be empty — T053a), so lookup_field/lookup_url_kwarg are
    # declared purely as the signal HasRole checks for, and
    # check_object_permissions() is called explicitly below rather than via
    # GenericAPIView.get_object() (which would 404 on an empty queryset,
    # which is exactly the behavior FR-024/T053a forbids here).
    lookup_url_kwarg = "target_id"
    permission_classes = [HasRole(Role.COMPLIANCE_OFFICER, Role.SYSTEM_ADMINISTRATOR)]

    def get(self, request, target_type, target_id):
        self.check_object_permissions(request, None)

        queryset = AuditLog.objects.filter(target_type=target_type, target_id=target_id).order_by("timestamp", "id")
        serializer = AuditLogSerializer(queryset, many=True)

        return Response(
            {
                "target_type": target_type,
                "target_id": target_id,
                "count": queryset.count(),
                "results": serializer.data,
            }
        )
