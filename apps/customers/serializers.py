"""
The single definition of customer validity (FR-009 through FR-014).

Both the API and the CSV loader construct these serializers rather than
writing models directly, so FR-038's "the load MUST apply the same
validation rules" holds by construction rather than by two definitions
kept in step by hand.
"""
from decimal import Decimal

from rest_framework import serializers

from .models import Customer

MIN_AGE = 18
MAX_AGE = 120
MIN_SCORE = Decimal("0")
MAX_SCORE = Decimal("1")

# Fields shared by the read, create, and update shapes.
_CUSTOMER_FIELDS = [
    "id",
    "client_id",
    "name",
    "email",
    "phone",
    "age",
    "gender",
    "location",
    "lead_source",
    "risk_score",
    "fraud_risk_flag",
    "cross_sell_score",
    "created_at",
    "updated_at",
]

# risk_score is read-only (FR-056; Phase 3a data-model.md): the risk
# engine is the sole writer now, mirroring RiskAssessment.score. An API
# client setting it directly would create a score with no assessment and
# no explanation -- a black-box score, which Principle IV forbids.
_READ_ONLY = ["id", "created_at", "updated_at", "risk_score"]


def _validate_unique_client_id(value, instance=None):
    """
    FR-003 / FR-021.

    Checked against all_objects, not the default manager: archival reserves
    the reference, so a collision with an archived record is still a
    collision. Using `objects` here would let a create succeed validation
    and then fail at the database with an IntegrityError on a row the
    serializer could not see.
    """
    queryset = Customer.all_objects.filter(client_id=value)
    if instance is not None:
        queryset = queryset.exclude(pk=instance.pk)
    if queryset.exists():
        raise serializers.ValidationError(
            f"A customer with reference {value} already exists."
        )
    return value


class CustomerSerializer(serializers.ModelSerializer):
    """Read + create shape, and the shape the CSV loader validates through."""

    # required=False so FR-005 generation can supply it; allow_null keeps a
    # blank CSV cell from being a hard error before generation runs.
    client_id = serializers.CharField(max_length=16, required=False, allow_null=True)
    name = serializers.CharField(max_length=255, trim_whitespace=True)
    age = serializers.IntegerField(min_value=MIN_AGE, max_value=MAX_AGE)
    cross_sell_score = serializers.DecimalField(
        max_digits=3,
        decimal_places=2,
        min_value=MIN_SCORE,
        max_value=MAX_SCORE,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Customer
        fields = _CUSTOMER_FIELDS
        read_only_fields = _READ_ONLY

    def validate_client_id(self, value):
        # A blank or null reference never reaches here -- CharField rejects
        # both first, which is what refuses a corrupt source row rather
        # than silently generating a reference for it. Generation happens
        # in create() when the key is absent entirely.
        return _validate_unique_client_id(value, instance=self.instance)

    def create(self, validated_data):
        # Drop an explicit null so create_with_reference generates one.
        if validated_data.get("client_id") is None:
            validated_data.pop("client_id", None)
        return Customer.objects.create_with_reference(**validated_data)


class CustomerUpdateSerializer(CustomerSerializer):
    """
    PATCH shape. Every field optional (FR-016), same validation rules.

    client_id stays writable so FR-003's conflict case is reachable through
    the API and reported as a field error rather than a 500.
    """

    class Meta(CustomerSerializer.Meta):
        extra_kwargs = {
            "name": {"required": False},
            "email": {"required": False},
            "phone": {"required": False},
            "age": {"required": False},
            "gender": {"required": False},
            "location": {"required": False},
            "lead_source": {"required": False},
        }
