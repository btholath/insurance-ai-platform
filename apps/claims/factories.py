from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.policies.factories import PolicyFactory

from .models import AnomalyStatus, Claim, ClaimLoadAnomaly, ClaimStatus, ClearedReason


class ClaimFactory(DjangoModelFactory):
    class Meta:
        model = Claim
        skip_postgeneration_save = True

    # SubFactory: a test needing several claims against ONE policy must
    # pass policy= explicitly, otherwise each claim gets its own policy and
    # the FR-003 multi-claim case is never exercised.
    policy = factory.SubFactory(PolicyFactory)

    claim_status = ClaimStatus.FILED

    # Deliberately non-zero by default. Zero is a legitimate value (FR-011)
    # and has its own explicit tests -- defaulting to it here would make
    # every amount assertion pass vacuously.
    claim_amount_usd = Decimal("1204.55")

    archived_at = None

    class Params:
        archived = factory.Trait(archived_at=factory.LazyFunction(timezone.now))
        approved = factory.Trait(claim_status=ClaimStatus.APPROVED)
        denied = factory.Trait(claim_status=ClaimStatus.DENIED)
        zero_amount = factory.Trait(claim_amount_usd=Decimal("0.00"))

    @classmethod
    def _get_manager(cls, model_class):
        # all_objects so archived claims can be built directly; the default
        # manager would hide them from any get_or_create path.
        return model_class.all_objects


class ClaimLoadAnomalyFactory(DjangoModelFactory):
    class Meta:
        model = ClaimLoadAnomaly
        skip_postgeneration_save = True

    policy = factory.SubFactory(PolicyFactory)

    # What the source said -- a value the Claim model refuses to represent.
    source_status = "No Claim"
    source_amount_usd = Decimal("19919.13")

    status = AnomalyStatus.OPEN
    cleared_reason = None
    cleared_at = None

    first_observed_at = factory.LazyFunction(timezone.now)
    last_observed_at = factory.LazyFunction(timezone.now)
    source_file = "data/Insurance_Dataset.csv"

    class Params:
        cleared_corrected = factory.Trait(
            status=AnomalyStatus.CLEARED,
            cleared_reason=ClearedReason.CORRECTED,
            cleared_at=factory.LazyFunction(timezone.now),
        )
        cleared_absent = factory.Trait(
            status=AnomalyStatus.CLEARED,
            cleared_reason=ClearedReason.ABSENT,
            cleared_at=factory.LazyFunction(timezone.now),
        )
