"""
Risk assessment API (T036-T039 US1, T046-T048 US6, T064-T065 US3).

A risk assessment is a judgment about a person, more sensitive than the
customer record it derives from (contracts/risk-assessment-api.md). This
is why VIEW_ROLES and RECOMPUTE_ROLES are wired from the start rather than
left open during US1 alone -- US1 and US6 together are the minimum
defensible increment (tasks.md Phase 4 checkpoint).

Fourth distinct role shape against Customer's 7, Policy's 8 and Claim's 5:
five roles read, two recompute. Customer Service reads customers but not
their risk assessments -- the divergence that makes this a genuinely
different set rather than a subset of Claim's.
"""
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.permissions import HasRole

from . import engine
from .models import RiskAssessment
from .serializers import RiskAssessmentSerializer

VIEW_ROLES = (
    Role.RISK_MANAGER,
    Role.UNDERWRITER,
    Role.FRAUD_ANALYST,
    Role.COMPLIANCE_OFFICER,
    Role.SYSTEM_ADMINISTRATOR,
)

RECOMPUTE_ROLES = (Role.RISK_MANAGER, Role.SYSTEM_ADMINISTRATOR)


class RiskAssessmentPagination(PageNumberPagination):
    page_size = 50


class RiskAssessmentViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = RiskAssessment.objects.select_related(
        "customer", "computed_by"
    ).prefetch_related("factors", "customer__policies", "customer__policies__claims")
    serializer_class = RiskAssessmentSerializer
    pagination_class = RiskAssessmentPagination

    def get_permissions(self):
        roles = RECOMPUTE_ROLES if self.action == "recompute" else VIEW_ROLES
        return [HasRole(*roles)()]

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params

        tier = params.get("tier")
        if tier:
            queryset = queryset.filter(tier=tier)

        customer = params.get("customer")
        if customer:
            queryset = queryset.filter(customer_id=customer)

        min_score = params.get("min_score")
        if min_score is not None:
            queryset = queryset.filter(score__gte=min_score)

        max_score = params.get("max_score")
        if max_score is not None:
            queryset = queryset.filter(score__lte=max_score)

        return queryset.order_by("id")

    def get_object(self):
        """
        FR-045: normalise DRF's Http404 to NotFound(), so a refusal 404
        and a genuine-miss 404 are byte-identical -- following
        ClaimViewSet.get_object(), not the shared exception handler
        (FR-041).
        """
        try:
            return super().get_object()
        except Http404:
            raise NotFound()

    @action(detail=False, methods=["get"], url_path="by-customer/(?P<customer_id>[^/.]+)")
    def by_customer(self, request, customer_id=None):
        """
        FR-029: a 404 here must be distinguishable from a low score, but
        FR-045 forbids that message becoming an existence oracle for a
        caller who cannot read risk at all -- so the distinguishing detail
        is returned only once has_permission has already let the caller
        through.
        """
        try:
            assessment = self.get_queryset().get(customer_id=customer_id)
        except RiskAssessment.DoesNotExist:
            raise NotFound({"detail": "This customer has not been assessed."})

        return Response(self.get_serializer(assessment).data)

    @action(detail=False, methods=["post"])
    def recompute(self, request):
        """
        FR-034: recompute exactly one customer, on demand. The only write
        route this feature adds (contracts/risk-assessment-api.md).
        """
        from apps.customers.models import Customer

        customer_id = request.data.get("customer")
        try:
            customer = Customer.objects.get(pk=customer_id)
        except (Customer.DoesNotExist, ValueError, TypeError):
            raise NotFound()

        policies = list(customer.policies.all())
        if not policies:
            return Response(
                {
                    "detail": (
                        f"Customer {customer.client_id} has no live policy, "
                        "so a risk score cannot be computed."
                    )
                },
                status=422,
            )

        with transaction.atomic():
            result = engine.score_customer(customer)
            assessment = engine.persist(customer, result, actor=request.user)

        return Response(self.get_serializer(assessment).data)
