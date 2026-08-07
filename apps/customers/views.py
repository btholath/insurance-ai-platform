"""
Customer API (FR-015 through FR-024, FR-027 through FR-031).

RBAC is applied per action rather than per viewset: seven roles may read,
only Customer Service and System Administrator may write (FR-024). Audit
writes happen inside the same transaction as the change they describe
(FR-031), following the pattern established in apps/accounts/views.py.
"""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.audit.services import record_action
from apps.core.permissions import HasRole

from .models import Customer
from .serializers import CustomerSerializer, CustomerUpdateSerializer

VIEW_ROLES = (
    Role.CUSTOMER_SERVICE,
    Role.SYSTEM_ADMINISTRATOR,
    Role.UNDERWRITER,
    Role.CLAIMS_ADJUSTER,
    Role.FRAUD_ANALYST,
    Role.RISK_MANAGER,
    Role.COMPLIANCE_OFFICER,
)
WRITE_ROLES = (Role.CUSTOMER_SERVICE, Role.SYSTEM_ADMINISTRATOR)

WRITE_ACTIONS = {"create", "update", "partial_update", "destroy"}

AUDITED_FIELDS = [
    "client_id", "name", "email", "phone", "age", "gender", "location",
    "lead_source", "risk_score", "fraud_risk_flag", "cross_sell_score",
]


def snapshot(customer):
    """JSON-safe field values for audit before/after payloads."""
    data = {}
    for field in AUDITED_FIELDS:
        value = getattr(customer, field)
        data[field] = str(value) if value is not None and field.endswith("_score") else value
    return data


class CustomerPagination(PageNumberPagination):
    page_size = 50


class CustomerViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    # Customer.objects excludes archived rows, so FR-020's invisibility and
    # FR-022's non-disclosure both fall out of the manager rather than
    # needing a branch in every handler.
    queryset = Customer.objects.all()
    pagination_class = CustomerPagination

    def get_permissions(self):
        roles = WRITE_ROLES if self.action in WRITE_ACTIONS else VIEW_ROLES
        return [HasRole(*roles)()]

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return CustomerUpdateSerializer
        return CustomerSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(email__icontains=search)
                | Q(client_id__icontains=search)
            )

        for param in ("lead_source", "gender", "fraud_risk_flag"):
            value = self.request.query_params.get(param)
            if value:
                queryset = queryset.filter(**{param: value})

        return queryset.order_by("id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            customer = serializer.save()
            record_action(
                actor=request.user,
                action="customer.created",
                target_type="customers.Customer",
                target_id=customer.id,
                outcome="succeeded",
                before=None,
                after=snapshot(customer),
            )

        return Response(CustomerSerializer(customer).data, status=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        customer = self.get_object()
        before_values = snapshot(customer)

        serializer = self.get_serializer(customer, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            updated = serializer.save()
            after_values = snapshot(updated)

            # FR-028: record only the fields that actually changed. A PATCH
            # setting a field to its current value contributes nothing.
            before_diff = {k: v for k, v in before_values.items() if v != after_values[k]}
            after_diff = {k: after_values[k] for k in before_diff}

            record_action(
                actor=request.user,
                action="customer.updated",
                target_type="customers.Customer",
                target_id=updated.id,
                outcome="succeeded",
                before=before_diff or None,
                after=after_diff or None,
            )

        return Response(CustomerSerializer(updated).data)

    def destroy(self, request, *args, **kwargs):
        """FR-020: reversible archival, never a row deletion."""
        customer = self.get_object()
        before_values = snapshot(customer)

        with transaction.atomic():
            customer.archived_at = timezone.now()
            customer.save(update_fields=["archived_at", "updated_at"])
            record_action(
                actor=request.user,
                action="customer.deleted",
                target_type="customers.Customer",
                target_id=customer.id,
                outcome="succeeded",
                before=before_values,
                after=None,
            )

        return Response(status=204)
