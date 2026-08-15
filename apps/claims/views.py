"""
Claims API (FR-016 through FR-032) and the read-only anomalies API (FR-047).

Replaces the Phase 1 PlaceholderView (FR-049). The placeholder's role set
(Claims Adjuster, Fraud Analyst, Sys Admin) is deliberately NOT inherited:
reads add Compliance Officer and Risk Manager, and writes DROP Fraud
Analyst, because investigation is not adjudication.

This read set is narrower than either prior module -- five roles, against
Customer's seven and Policy's eight. Claim amounts are financial detail
about an individual, so product- and sales-facing roles are excluded. The
sharp case: an Underwriter may WRITE policies but may not READ claims, so
their 404 on a claim is a refusal while their 404 on a policy is an
ordinary miss. That distinction is what the per-module audit registry
exists for.

Audit writes happen inside the same transaction as the change they
describe (FR-034), following apps/policies/views.py.
"""
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.audit.services import record_action
from apps.core.permissions import HasRole

from .models import Claim, ClaimLoadAnomaly
from .serializers import (
    ClaimLoadAnomalySerializer,
    ClaimSerializer,
    ClaimUpdateSerializer,
)

# Five roles read: claim handling, fraud investigation, compliance review,
# risk management, system administration (FR-026).
VIEW_ROLES = (
    Role.CLAIMS_ADJUSTER,
    Role.FRAUD_ANALYST,
    Role.COMPLIANCE_OFFICER,
    Role.RISK_MANAGER,
    Role.SYSTEM_ADMINISTRATOR,
)

# Two roles write (FR-027). A Fraud Analyst investigates claims but does
# not adjudicate them, so read without write is the correct shape.
WRITE_ROLES = (Role.CLAIMS_ADJUSTER, Role.SYSTEM_ADMINISTRATOR)

WRITE_ACTIONS = {"create", "update", "partial_update", "destroy"}

AUDITED_FIELDS = ["policy_id", "claim_status", "claim_amount_usd"]


def snapshot(claim):
    """JSON-safe field values for audit before/after payloads."""
    return {
        "policy_id": claim.policy_id,
        "claim_status": claim.claim_status,
        "claim_amount_usd": str(claim.claim_amount_usd),
    }


class ClaimPagination(PageNumberPagination):
    page_size = 50


class ClaimViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    # Claim.objects excludes archived CLAIMS, so FR-021's invisibility and
    # FR-028's non-disclosure both fall out of the manager.
    #
    # Note it does NOT exclude claims whose POLICY is archived: a claim
    # against an archived policy stays visible, which is what FR-008
    # requires and is the reverse of the instinct to hide it.
    # select_related resolves the policy through the FK (which ignores the
    # default manager), so an archived policy still resolves -- and keeps
    # the embedded summary from becoming an N+1 across a 50-record page.
    queryset = Claim.objects.select_related("policy", "policy__customer").all()
    pagination_class = ClaimPagination

    def get_permissions(self):
        roles = WRITE_ROLES if self.action in WRITE_ACTIONS else VIEW_ROLES
        return [HasRole(*roles)()]

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return ClaimUpdateSerializer
        return ClaimSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        policy = params.get("policy")
        if policy:
            queryset = queryset.filter(policy_id=policy)

        claim_status = params.get("claim_status")
        if claim_status:
            queryset = queryset.filter(claim_status=claim_status)

        return queryset.order_by("id")

    def get_object(self):
        """
        FR-028 / SC-006: the refusal 404 and the genuine-miss 404 must be
        INDISTINGUISHABLE, body included -- not merely the same status.

        DRF's get_object_or_404 raises Http404 with "No Claim matches the
        given query.", while HasRole's refusal raises NotFound() with
        "Not found.". Same status, different body: a caller who may not
        read claims could tell an existing claim from a missing one by
        reading the message, which is exactly what FR-028 forbids.

        Normalising here rather than in apps/core/exception_handlers.py is
        deliberate -- FR-030 requires that shared handler stay untouched.
        """
        try:
            return super().get_object()
        except Http404:
            raise NotFound()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            claim = serializer.save()
            record_action(
                actor=request.user,
                action="claim.created",
                target_type="claims.Claim",
                target_id=claim.id,
                outcome="succeeded",
                before=None,
                after=snapshot(claim),
            )

        return Response(ClaimSerializer(claim).data, status=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        claim = self.get_object()
        before_values = snapshot(claim)

        serializer = self.get_serializer(claim, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            updated = serializer.save()
            after_values = snapshot(updated)

            # FR-033: record only the fields that actually changed. A PATCH
            # setting a status to the value it already has contributes
            # nothing -- an empty diff, not a fabricated one.
            before_diff = {k: v for k, v in before_values.items() if v != after_values[k]}
            after_diff = {k: after_values[k] for k in before_diff}

            record_action(
                actor=request.user,
                action="claim.updated",
                target_type="claims.Claim",
                target_id=updated.id,
                outcome="succeeded",
                before=before_diff or None,
                after=after_diff or None,
            )

        return Response(ClaimSerializer(updated).data)

    def destroy(self, request, *args, **kwargs):
        """
        FR-021: reversible archival, never a row deletion.

        Archiving a claim releases nothing and reserves nothing -- there is
        no uniqueness constraint to interact with (FR-007). This is the
        substantive difference from both prior modules, where archival had
        a slot-management consequence.
        """
        claim = self.get_object()
        before_values = snapshot(claim)

        with transaction.atomic():
            claim.archived_at = timezone.now()
            claim.save(update_fields=["archived_at", "updated_at"])
            record_action(
                actor=request.user,
                action="claim.deleted",
                target_type="claims.Claim",
                target_id=claim.id,
                outcome="succeeded",
                before=before_values,
                after=None,
            )

        return Response(status=204)


class ClaimLoadAnomalyViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    Read-only (FR-047). The loader is the only writer.

    No create/update/destroy, and deliberately no manual clear or dismiss
    action: an anomaly clears only because a later load observed something,
    never because a person decided it was fine. A dismiss button would be
    indistinguishable, one export later, from a verified correction --
    exactly the conflation FR-044a forbids.
    """

    queryset = ClaimLoadAnomaly.objects.select_related(
        "policy", "policy__customer"
    ).all()
    serializer_class = ClaimLoadAnomalySerializer
    pagination_class = ClaimPagination

    def get_permissions(self):
        # Exactly the claim READ set. An anomaly discloses claim-adjacent
        # financial detail, so it cannot be readable by anyone who may not
        # read claims.
        return [HasRole(*VIEW_ROLES)()]

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        policy = params.get("policy")
        if policy:
            queryset = queryset.filter(policy_id=policy)

        status = params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        # The filter FR-044a exists for: a consumer counting confirmed
        # corrections MUST be able to exclude absent-cleared anomalies.
        cleared_reason = params.get("cleared_reason")
        if cleared_reason:
            queryset = queryset.filter(cleared_reason=cleared_reason)

        return queryset.order_by("id")

    def get_object(self):
        """Same non-disclosure normalisation as ClaimViewSet (FR-047)."""
        try:
            return super().get_object()
        except Http404:
            raise NotFound()
