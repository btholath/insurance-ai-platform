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
    factors = RiskFactorSerializer(many=True, read_only=True)
    client_id = serializers.CharField(source="customer.client_id", read_only=True)
    tier_label = serializers.SerializerMethodField()
    computed_by = serializers.SlugRelatedField(slug_field="email", read_only=True)

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
            "factors",
        ]
        read_only_fields = fields

    def get_tier_label(self, obj):
        return RiskTier(obj.tier).label
