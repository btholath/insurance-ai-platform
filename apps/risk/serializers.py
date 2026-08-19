"""
Read shapes for the risk API (T034-T035, FR-019, FR-020, FR-023, FR-025,
FR-026, FR-027).

No write serializer exists here, deliberately (contracts/risk-assessment-
api.md, "Routes deliberately absent"): a score is engine output, never
user input.
"""
from rest_framework import serializers

from .models import RiskAssessment, RiskFactor, RiskFactorName, RiskTier


class RiskFactorSerializer(serializers.ModelSerializer):
    factor_label = serializers.SerializerMethodField()

    class Meta:
        model = RiskFactor
        fields = [
            "factor",
            "factor_label",
            "status",
            "observed_value",
            "band_label",
            "points",
            "unevaluable_reason",
        ]
        read_only_fields = fields

    def get_factor_label(self, obj):
        return RiskFactorName(obj.factor).label


class RiskAssessmentSerializer(serializers.ModelSerializer):
    """
    is_stale/stale_reason are derived on read (T070), never stored (see
    the model's "Deliberate non-fields" in data-model.md): a stored flag
    has no honest writer in a phase that forbids automatic recomputation,
    and a flag that says "fresh" forever is worse than no flag.

    Over-reports deliberately (research §4) -- any change to the
    customer, a live policy, or a live claim marks the assessment stale,
    including changes to fields no factor reads. Over-reporting is the
    safe direction; the alternative is a stale score presented as fresh.
    """

    factors = RiskFactorSerializer(many=True, read_only=True)
    client_id = serializers.CharField(source="customer.client_id", read_only=True)
    tier_label = serializers.SerializerMethodField()
    computed_by = serializers.SlugRelatedField(slug_field="email", read_only=True)
    is_stale = serializers.SerializerMethodField()
    stale_reason = serializers.SerializerMethodField()

    class Meta:
        model = RiskAssessment
        fields = [
            "id",
            "customer",
            "client_id",
            "score",
            "tier",
            "tier_label",
            "rule_set_version",
            "computed_at",
            "computed_by",
            "is_stale",
            "stale_reason",
            "factors",
        ]
        read_only_fields = fields

    def get_tier_label(self, obj):
        return RiskTier(obj.tier).label

    def _is_stale(self, obj):
        """
        Compares against the customer's own `updated_at` fetched fresh
        (a single cheap row lookup), rather than `obj.customer.updated_at`
        -- that relation may be cached from whenever `obj` was fetched
        (e.g. the viewset's select_related), which can predate a write
        that happened afterward in the same request/test. Policies and
        claims are read through the prefetched relation, which T071's
        prefetch_related keeps off the N+1 path for the list route.
        """
        from apps.customers.models import Customer

        customer_updated_at = (
            Customer.objects.filter(pk=obj.customer_id)
            .values_list("updated_at", flat=True)
            .first()
        )
        if customer_updated_at is not None and customer_updated_at > obj.computed_at:
            return True

        for policy in obj.customer.policies.all():
            if policy.updated_at > obj.computed_at:
                return True
            for claim in policy.claims.all():
                if claim.updated_at > obj.computed_at:
                    return True
        return False

    def get_is_stale(self, obj):
        return self._is_stale(obj)

    def get_stale_reason(self, obj):
        if not self._is_stale(obj):
            return None
        return "Customer or policy data changed after this assessment was computed"

    def to_representation(self, instance):
        """FR-039: stale_reason present only when is_stale is true."""
        data = super().to_representation(instance)
        if not data["is_stale"]:
            data.pop("stale_reason", None)
        return data
