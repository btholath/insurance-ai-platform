from django.db import transaction
from rest_framework import mixins, viewsets
from rest_framework.pagination import PageNumberPagination

from apps.audit.services import record_action
from apps.core.permissions import HasRole

from .models import Role, User
from .serializers import UserCreateSerializer, UserSerializer, UserUpdateSerializer


class UserListPagination(PageNumberPagination):
    page_size = 50


class UserViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = User.objects.all().order_by("id")
    permission_classes = [HasRole(Role.SYSTEM_ADMINISTRATOR)]
    pagination_class = UserListPagination

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in ("update", "partial_update"):
            return UserUpdateSerializer
        return UserSerializer

    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            response = super().create(request, *args, **kwargs)
            created = User.objects.get(pk=response.data["id"])
            record_action(
                actor=request.user,
                action="user.created",
                target_type="accounts.User",
                target_id=created.id,
                outcome="succeeded",
                before=None,
                after={"email": created.email, "role": created.role, "is_active": created.is_active},
            )
        response.data = UserSerializer(created).data
        return response

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        before_role, before_active = instance.role, instance.is_active

        with transaction.atomic():
            response = super().partial_update(request, *args, **kwargs)
            instance.refresh_from_db()

            before, after = {}, {}
            if "role" in request.data and instance.role != before_role:
                before["role"], after["role"] = before_role, instance.role
            if "is_active" in request.data and instance.is_active != before_active:
                before["is_active"], after["is_active"] = before_active, instance.is_active

            if after.get("is_active") is False:
                action_name = "user.deactivated"
            elif "role" in after:
                action_name = "user.role_changed"
            else:
                action_name = "user.updated"

            record_action(
                actor=request.user,
                action=action_name,
                target_type="accounts.User",
                target_id=instance.id,
                outcome="succeeded",
                before=before or None,
                after=after or None,
            )
        response.data = UserSerializer(instance).data
        return response
