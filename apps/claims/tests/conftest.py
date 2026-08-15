import pytest

from apps.claims.factories import ClaimFactory, ClaimLoadAnomalyFactory


@pytest.fixture
def claim_factory():
    """ClaimFactory as a fixture, so tests read as behaviour not construction."""
    return ClaimFactory


@pytest.fixture
def anomaly_factory():
    return ClaimLoadAnomalyFactory
