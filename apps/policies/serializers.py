"""
The single definition of policy validity (FR-009 through FR-015).

Both the API and the dataset loader construct these serializers rather than
writing models directly, so FR-043's "the load MUST apply the same
validation rules" holds by construction rather than by two definitions kept
in step by hand.
"""
from decimal import Decimal

from rest_framework import serializers

from apps.customers.models import Customer

from .models import Policy, PolicyType

MIN_SCORE = Decimal("0")
MAX_SCORE = Decimal("1")
MIN_PREMIUM = Decimal("0.01")


class CustomerSummarySerializer(serializers.ModelSerializer):
    """Minimal customer shape embedded in policy responses (US1)."""

    class Meta:
        model = Customer
        fields = ["id", "client_id", "name"]
        read_only_fields = fields


class ArchivedAwarePrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """
    Resolves customers through all_objects, then refuses archived ones with
    a message that says so (FR-013, FR-014).

    Resolving through Customer.objects instead would hide archived rows and
    report "does not exist" for a customer that was deliberately removed --
    sending an underwriter hunting for a record that is right there.
    """

    def get_queryset(self):
        return Customer.all_objects.all()

    def to_internal_value(self, data):
        customer = super().to_internal_value(data)
        if customer.archived_at is not None:
            raise serializers.ValidationError(
                f"Customer {customer.client_id} has been archived and cannot take new policies."
            )
        return customer


class PolicySerializer(serializers.ModelSerializer):
    """Read + create shape, and the shape the dataset loader validates through."""

    customer = ArchivedAwarePrimaryKeyRelatedField()
    premium_usd = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=MIN_PREMIUM
    )
    renewal_probability = serializers.DecimalField(
        max_digits=3,
        decimal_places=2,
        min_value=MIN_SCORE,
        max_value=MAX_SCORE,
        required=False,
        allow_null=True,
    )
    policy_type = serializers.ChoiceField(choices=PolicyType.choices)

    class Meta:
        model = Policy
        fields = [
            "id",
            "customer",
            "policy_type",
            "start_date",
            "end_date",
            "premium_usd",
            "renewal_probability",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        # ModelSerializer would otherwise synthesize a
        # UniqueTogetherValidator from the model's UniqueConstraint. It
        # reports under non_field_errors, which violates FR-015's "name the
        # offending field", and it runs BEFORE validate() so our own
        # message never gets the chance. The check lives in validate()
        # instead, where it can name policy_type.
        validators = []

    def to_representation(self, instance):
        """Embed the customer summary on read so US1 needs no second request."""
        data = super().to_representation(instance)
        data["customer"] = CustomerSummarySerializer(instance.customer).data
        return data

    def validate(self, attrs):
        """
        Cross-field rules live here rather than in field validators -- that
        is what lets the FR-010 error name both dates rather than one.
        """
        start = attrs.get("start_date") or getattr(self.instance, "start_date", None)
        end = attrs.get("end_date") or getattr(self.instance, "end_date", None)

        if start and end and end <= start:
            raise serializers.ValidationError(
                {
                    "start_date": "Start date must be before end date.",
                    "end_date": "End date must be after start date.",
                }
            )

        customer = attrs.get("customer") or getattr(self.instance, "customer", None)
        policy_type = attrs.get("policy_type") or getattr(self.instance, "policy_type", None)

        if customer and policy_type:
            clash = Policy.objects.filter(customer=customer, policy_type=policy_type)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {
                        "policy_type": (
                            f"{customer.client_id} already holds a live {policy_type} policy."
                        )
                    }
                )

        return attrs


class PolicyUpdateSerializer(PolicySerializer):
    """PATCH shape. Every field optional (FR-017), same rules."""

    class Meta(PolicySerializer.Meta):
        extra_kwargs = {
            "customer": {"required": False},
            "policy_type": {"required": False},
            "start_date": {"required": False},
            "end_date": {"required": False},
            "premium_usd": {"required": False},
        }
