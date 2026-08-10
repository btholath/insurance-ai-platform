"""
Policy API (FR-016 through FR-023, FR-026 through FR-033).

Two role decisions here are deliberately the reverse of the customer
module, and are pinned by tests so neither is later "harmonized" away:

1. Writes are Underwriter + System Administrator, not Customer Service.
   Setting policy terms is underwriting work.
2. Product Manager may READ policies though they may not read customers.
   Product mix is a product concern; individual personal data is not.

Audit writes happen inside the same transaction as the change they
describe (FR-033), following the pattern established in
apps/customers/views.py.
"""
from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.audit.services import record_action
from apps.core.permissions import HasRole

from .models import Policy
from .serializers import PolicySerializer, PolicyUpdateSerializer

# Eight roles read: everyone except Executive Leadership.
VIEW_ROLES = (
    Role.CUSTOMER_SERVICE,
    Role.SYSTEM_ADMINISTRATOR,
    Role.UNDERWRITER,
    Role.CLAIMS_ADJUSTER,
    Role.FRAUD_ANALYST,
    Role.RISK_MANAGER,
    Role.COMPLIANCE_OFFICER,
    Role.PRODUCT_MANAGER,
)
WRITE_ROLES = (Role.UNDERWRITER, Role.SYSTEM_ADMINISTRATOR)

WRITE_ACTIONS = {"create", "update", "partial_update", "destroy"}

AUDITED_FIELDS = [
    "customer_id", "policy_type", "start_date", "end_date",
    "premium_usd", "renewal_probability",
]


def snapshot(policy):
    """JSON-safe field values for audit before/after payloads."""
    data = {}
    for field in AUDITED_FIELDS:
        value = getattr(policy, field)
        if value is None:
            data[field] = None
        elif field in ("start_date", "end_date"):
            data[field] = value.isoformat()
        elif field in ("premium_usd", "renewal_probability"):
            data[field] = str(value)
        else:
            data[field] = value
    return data


class PolicyPagination(PageNumberPagination):
    page_size = 50


class PolicyViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    # Policy.objects excludes archived rows, so FR-021's invisibility and
    # FR-023's non-disclosure both fall out of the manager rather than
    # needing a branch in every handler.
    #
    # select_related keeps the embedded customer summary from becoming an
    # N+1 across a 50-record page.
    queryset = Policy.objects.select_related("customer").all()
    pagination_class = PolicyPagination

    def get_permissions(self):
        roles = WRITE_ROLES if self.action in WRITE_ACTIONS else VIEW_ROLES
        return [HasRole(*roles)()]

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return PolicyUpdateSerializer
        return PolicySerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        customer = params.get("customer")
        if customer:
            queryset = queryset.filter(customer_id=customer)

        policy_type = params.get("policy_type")
        if policy_type:
            queryset = queryset.filter(policy_type=policy_type)

        # Expiry is derived per request rather than stored (FR-020): a
        # stored flag would be wrong the day after it was written unless
        # something maintained it, and that job's failure mode is silently
        # stale data.
        expired = params.get("expired")
        if expired is not None:
            today = timezone.localdate()
            if expired.lower() in ("true", "1", "yes"):
                queryset = queryset.filter(end_date__lt=today)
            elif expired.lower() in ("false", "0", "no"):
                queryset = queryset.filter(end_date__gte=today)

        return queryset.order_by("id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            policy = serializer.save()
            record_action(
                actor=request.user,
                action="policy.created",
                target_type="policies.Policy",
                target_id=policy.id,
                outcome="succeeded",
                before=None,
                after=snapshot(policy),
            )

        return Response(PolicySerializer(policy).data, status=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        policy = self.get_object()
        before_values = snapshot(policy)

        serializer = self.get_serializer(policy, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            updated = serializer.save()
            after_values = snapshot(updated)

            # FR-029: record only the fields that actually changed. A PATCH
            # setting a field to its current value contributes nothing.
            before_diff = {k: v for k, v in before_values.items() if v != after_values[k]}
            after_diff = {k: after_values[k] for k in before_diff}

            record_action(
                actor=request.user,
                action="policy.updated",
                target_type="policies.Policy",
                target_id=updated.id,
                outcome="succeeded",
                before=before_diff or None,
                after=after_diff or None,
            )

        return Response(PolicySerializer(updated).data)

    def destroy(self, request, *args, **kwargs):
        """
        FR-021: reversible archival, never a row deletion.

        Archiving releases the (customer, policy_type) slot, so the
        customer may hold a new policy of that type -- deliberately the
        opposite of Customer, where an archived client_id stays reserved.
        """
        policy = self.get_object()
        before_values = snapshot(policy)

        with transaction.atomic():
            policy.archived_at = timezone.now()
            policy.save(update_fields=["archived_at", "updated_at"])
            record_action(
                actor=request.user,
                action="policy.deleted",
                target_type="policies.Policy",
                target_id=policy.id,
                outcome="succeeded",
                before=before_values,
                after=None,
            )

        return Response(status=204)
