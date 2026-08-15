"""
The single definition of claim validity (FR-010 through FR-015).

Both the API and the dataset loader construct these serializers rather than
writing models directly, so the loader's validation and the API's hold by
construction rather than by two definitions kept in step by hand -- the
same arrangement Phase 2b established for policies.

One asymmetry the loader must respect: `No Claim` is a VALID source value
but is not a valid claim status, so the loader branches on it BEFORE
constructing a serializer. Feeding it here would report a validation error
for a row that is not invalid. See the loaddataset command.
"""
from decimal import Decimal

from rest_framework import serializers

from apps.customers.models import Customer
from apps.policies.models import Policy

from .models import Claim, ClaimLoadAnomaly, ClaimStatus

MIN_AMOUNT = Decimal("0")

# The message an adjuster sees when they submit `No Claim`. Deliberately
# more than "not a valid choice": the absence of a claim is a modelling
# decision (FR-004), and an error that does not explain it reads as a bug.
NO_CLAIM_MESSAGE = (
    "'No Claim' is not a claim status. The absence of a claim is represented "
    "by the absence of a claim record, not by a record whose status denies "
    "its own existence."
)


class CustomerSummarySerializer(serializers.ModelSerializer):
    """Minimal customer shape, reached only through the policy (FR-002)."""

    class Meta:
        model = Customer
        fields = ["id", "client_id", "name"]
        read_only_fields = fields


class PolicySummarySerializer(serializers.ModelSerializer):
    """
    Minimal policy shape embedded in claim responses.

    Carries policy_type so US1 needs no second request to learn which
    coverage a claim relates to (FR-023).
    """

    customer = CustomerSummarySerializer(read_only=True)

    class Meta:
        model = Policy
        fields = ["id", "policy_type", "customer"]
        read_only_fields = fields


class ArchivedAwarePolicyField(serializers.PrimaryKeyRelatedField):
    """
    Resolves policies through all_objects, then refuses archived ones with
    a message that says so (FR-013, FR-014).

    Resolving through Policy.objects instead would hide archived rows and
    report "does not exist" for a policy that is right there -- sending an
    adjuster hunting for a record that was deliberately withdrawn.
    """

    def get_queryset(self):
        return Policy.all_objects.all()

    def to_internal_value(self, data):
        policy = super().to_internal_value(data)
        if policy.archived_at is not None:
            raise serializers.ValidationError(
                f"Policy {policy.pk} has been archived and cannot take new claims."
            )
        return policy


class ClaimStatusField(serializers.ChoiceField):
    """
    A ChoiceField whose invalid-choice message explains FR-004 when the
    submitted value is specifically `No Claim`.

    `No Claim` fails here by construction -- it is not in ClaimStatus at
    all -- so this override changes only the message, never the outcome.
    """

    def to_internal_value(self, data):
        if isinstance(data, str) and data.strip().lower() == "no claim":
            raise serializers.ValidationError(NO_CLAIM_MESSAGE)
        return super().to_internal_value(data)


class ClaimSerializer(serializers.ModelSerializer):
    """Read + create shape, and the shape the dataset loader validates through."""

    policy = ArchivedAwarePolicyField()
    claim_status = ClaimStatusField(choices=ClaimStatus.choices)
    # min_value rather than a validator: zero is legitimate (FR-011), so
    # the bound is gte 0, matching the claim_amount_non_negative constraint.
    claim_amount_usd = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=MIN_AMOUNT
    )

    class Meta:
        model = Claim
        fields = [
            "id",
            "policy",
            "claim_status",
            "claim_amount_usd",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def to_representation(self, instance):
        """Embed the policy summary on read so US1 needs no second request."""
        data = super().to_representation(instance)
        data["policy"] = PolicySummarySerializer(instance.policy).data
        return data


class ClaimUpdateSerializer(ClaimSerializer):
    """
    PATCH shape. Status and amount optional; policy read-only (FR-022).

    A claim cannot be moved between policies -- reassignment would silently
    rewrite the coverage context the claim was judged under, which is
    precisely the history the audit trail exists to preserve. Correcting a
    misfiled claim is a removal plus a new record, both audited.
    """

    policy = PolicySummarySerializer(read_only=True)

    class Meta(ClaimSerializer.Meta):
        extra_kwargs = {
            "claim_status": {"required": False},
            "claim_amount_usd": {"required": False},
        }


class ClaimLoadAnomalySerializer(serializers.ModelSerializer):
    """
    Read-only. The dataset loader is the only writer -- an anomaly is an
    observation of what the source said, not a record anyone authors.
    """

    policy = PolicySummarySerializer(read_only=True)

    class Meta:
        model = ClaimLoadAnomaly
        fields = [
            "id",
            "policy",
            "source_status",
            "source_amount_usd",
            "status",
            "cleared_reason",
            "cleared_at",
            "first_observed_at",
            "last_observed_at",
            "source_file",
        ]
        read_only_fields = fields
