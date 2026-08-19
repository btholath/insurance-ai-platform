"""
Rule-set tests (T006-T011a).

These are PURE FUNCTION tests -- no database, no fixtures, no ORM. That is
deliberate and is what makes them the fastest and highest-value tests in the
feature: the scoring rules are the business-rule core Principle V names
explicitly, and they can be exercised exhaustively without a single query.

Every band boundary is tested on BOTH sides. The convention under test is
lower-inclusive / upper-exclusive with the top band closed, so a customer aged
exactly 25 falls in the 25-34 band and never in "under 25" (FR-007).
"""
import pytest

from apps.risk import rules


# ---------------------------------------------------------------------------
# T006 -- age bands, both sides of every boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "age,expected_points,expected_band",
    [
        (18, 15, "under 25"),
        (24, 15, "under 25"),
        (25, 5, "25-34"),
        (34, 5, "25-34"),
        (35, 0, "35-49"),
        (49, 0, "35-49"),
        (50, 0, "50-64"),
        (64, 0, "50-64"),
        (65, 10, "65 and over"),
        (75, 10, "65 and over"),
        (120, 10, "65 and over"),
    ],
)
def test_age_bands(age, expected_points, expected_band):
    result = rules.score_age(age)
    assert result.points == expected_points
    assert result.band_label == expected_band
    assert result.status == rules.FactorStatus.EVALUATED


def test_age_boundaries_are_lower_inclusive():
    """24 and 25 must land in different bands -- the FR-007 edge case."""
    assert rules.score_age(24).band_label != rules.score_age(25).band_label
    assert rules.score_age(34).band_label != rules.score_age(35).band_label
    assert rules.score_age(64).band_label != rules.score_age(65).band_label


# ---------------------------------------------------------------------------
# T007 -- policy type, including the multi-policy rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "policy_type,expected_points",
    [("Auto", 15), ("Health", 10), ("Property", 5), ("Life", 0)],
)
def test_policy_type_bands(policy_type, expected_points):
    result = rules.score_policy_type([policy_type])
    assert result.points == expected_points
    assert result.band_label == policy_type


def test_policy_type_takes_the_highest_scoring_live_policy():
    """
    FR-008. The seeded export carries exactly one policy per customer, but the
    model permits many, so the combination rule is stated rather than left to
    the shape of one export. Worst-case wins for coverage type.
    """
    assert rules.score_policy_type(["Life", "Auto"]).points == 15
    assert rules.score_policy_type(["Life", "Property"]).points == 5
    assert rules.score_policy_type(["Health", "Property", "Life"]).points == 10


def test_policy_type_is_not_evaluable_without_a_policy():
    """FR-018: unknown is not the same as zero."""
    result = rules.score_policy_type([])
    assert result.status == rules.FactorStatus.NOT_EVALUABLE
    assert result.points == 0
    assert result.unevaluable_reason


# ---------------------------------------------------------------------------
# T008 -- claims history: three distinct outcomes
# ---------------------------------------------------------------------------


def test_claims_history_no_claim():
    result = rules.score_claims_history([])
    assert result.points == 0
    assert result.status == rules.FactorStatus.EVALUATED


def test_claims_history_zero_amount_claim_only():
    """
    FR-013. 1,143 of 2,246 seeded claims are exactly 0.00 -- an event that
    occurred but cost nothing. It must score as NEITHER "no claim" nor
    "a claim of substance".
    """
    result = rules.score_claims_history([_claim(0)])
    assert result.points == 5


def test_claims_history_non_zero_claim():
    result = rules.score_claims_history([_claim(500)])
    assert result.points == 20


def test_claims_history_three_outcomes_are_distinct():
    """The whole point of FR-013 -- all three must differ."""
    none = rules.score_claims_history([]).points
    zero = rules.score_claims_history([_claim(0)]).points
    real = rules.score_claims_history([_claim(1)]).points
    assert len({none, zero, real}) == 3


def test_claims_history_mixed_takes_the_non_zero_band():
    assert rules.score_claims_history([_claim(0), _claim(900)]).points == 20


# ---------------------------------------------------------------------------
# T009 -- claims ratio, both sides of every boundary, plus bounding
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ratio,expected_points",
    [
        (0.0, 0),
        (0.99, 0),
        (1.0, 10),
        (2.99, 10),
        (3.0, 20),
        (4.99, 20),
        (5.0, 30),
        (10.0, 30),
        (155.108, 30),  # the seeded maximum
    ],
)
def test_claims_ratio_bands(ratio, expected_points):
    assert rules.score_claims_ratio(ratio).points == expected_points


def test_claims_ratio_is_bounded_by_its_top_band():
    """
    FR-012. A single extreme ratio must not dominate the total. The seeded max
    is 155x premium; it contributes exactly the top band and no more.
    """
    assert rules.score_claims_ratio(155.108).points == rules.score_claims_ratio(5.0).points
    assert rules.score_claims_ratio(10_000).points == 30


def test_claims_ratio_not_evaluable_without_premium():
    result = rules.score_claims_ratio(None)
    assert result.status == rules.FactorStatus.NOT_EVALUABLE
    assert result.points == 0
    assert result.unevaluable_reason


# ---------------------------------------------------------------------------
# T010 -- denied claim, scored independently of claims history
# ---------------------------------------------------------------------------


def test_denied_claim_present():
    assert rules.score_denied_claim([_claim(100, "Denied")]).points == 10


def test_denied_claim_absent():
    assert rules.score_denied_claim([_claim(100, "Approved")]).points == 0


def test_denied_claim_no_claims_at_all():
    assert rules.score_denied_claim([]).points == 0


def test_denied_claim_is_independent_of_claims_history():
    """
    FR-014. A denied claim of 0.00 contributes to denial but lands in the
    zero-amount band for history -- the two factors must not be entangled.
    """
    claims = [_claim(0, "Denied")]
    assert rules.score_denied_claim(claims).points == 10
    assert rules.score_claims_history(claims).points == 5


# ---------------------------------------------------------------------------
# T011 -- tier thresholds, both sides of every boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (0, "low"),
        (19, "low"),
        (20, "moderate"),
        (39, "moderate"),
        (40, "elevated"),
        (59, "elevated"),
        (60, "high"),
        (100, "high"),
    ],
)
def test_tier_thresholds(score, expected):
    assert rules.tier_for(score) == expected


def test_every_score_maps_to_exactly_one_tier():
    """FR-006 / FR-007: no gap, no overlap, across the whole scale."""
    for score in range(0, rules.max_score() + 1):
        tier = rules.tier_for(score)
        assert tier is not None, f"score {score} mapped to no tier"
        matching = [t for t, lo, hi in rules.TIER_BANDS if lo <= score <= hi]
        assert len(matching) == 1, f"score {score} matched {len(matching)} tiers"


def test_max_score_equals_the_sum_of_factor_maxima():
    """
    FR-005: the scale is whatever the table sums to, and nothing else.

    The expected value is re-derived here from the band tables themselves --
    NOT from `rules._FACTOR_MAXIMA`, which is the same derivation `max_score`
    already uses and would make this a tautology. Reading the bands directly
    is what makes this test capable of failing: if a point value changes,
    both sides move together and the test stays green; if `max_score` stops
    summing the table -- restates a literal, drops a factor, double-counts
    one -- only the left side moves and this fails.

    A hardcoded number here is what let the prose claim 100 while the bands
    summed to 90. There is deliberately no literal scale in this file.
    """
    expected = (
        max(b.points for b in rules.AGE_BANDS)
        + max(points for _, points in rules.POLICY_TYPE_POINTS)
        + max(b.points for b in rules.CLAIMS_HISTORY_BANDS)
        + max(b.points for b in rules.CLAIMS_RATIO_BANDS)
        + max(b.points for b in rules.DENIED_CLAIM_BANDS)
    )
    assert rules.max_score() == expected


def test_max_score_covers_every_factor_in_the_set():
    """
    The sum above enumerates five band tables by hand, so it would still
    pass if a SIXTH factor were added to `FACTORS` and left out of the
    scale. This pins the enumeration to the factor set itself.
    """
    assert set(rules._FACTOR_MAXIMA) == set(rules.FACTORS)


# ---------------------------------------------------------------------------
# T011a -- the factor set is pinned by EXACT EQUALITY (FR-017)
# ---------------------------------------------------------------------------


APPROVED_FACTORS = {
    "age",
    "policy_type",
    "claims_history",
    "claims_ratio",
    "denied_claim",
}


def test_factor_set_is_exactly_the_approved_five():
    """
    FR-017 enforcement point. EQUALITY, not containment, in both directions:

      - a subset check would let an unapproved SIXTH factor through
      - a superset check would let an approved one be silently DROPPED

    FR-017 forbids gender and location as scoring factors, and forbids any
    factor incapable of discriminating in the seeded data. Without this
    assertion FR-017 lives only in prose (spec Assumptions, research §5, the
    rules.py docstring) and nothing fails when someone adds a `gender` band.

    Gender is a protected characteristic and its use in insurance risk scoring
    carries regulatory exposure. If this test fails, do NOT relax it -- amend
    FR-017 first, deliberately, or remove the offending factor.
    """
    assert set(rules.FACTORS) == APPROVED_FACTORS, (
        "FR-017 violation: the scoring factor set changed. "
        f"Expected exactly {sorted(APPROVED_FACTORS)}, "
        f"got {sorted(rules.FACTORS)}. "
        "Gender and location are forbidden as scoring factors; any new factor "
        "requires amending FR-017 and this test deliberately."
    )


def test_forbidden_characteristics_are_absent():
    """
    A named-and-shamed companion to the equality check above. Redundant by
    construction -- and kept anyway, because the failure message names the
    specific regulatory hazard rather than just reporting a set difference.
    """
    for forbidden in ("gender", "location", "lead_source", "fraud_risk_flag"):
        assert forbidden not in rules.FACTORS, (
            f"FR-017 violation: '{forbidden}' must never be a scoring factor."
        )


def test_evaluate_returns_exactly_one_result_per_factor():
    """FR-022: every factor is reported, including zero contributions."""
    results = rules.evaluate(
        age=40, policy_types=["Life"], claims=[], claims_ratio=0.0
    )
    assert len(results) == len(rules.FACTORS)
    assert {r.factor for r in results} == APPROVED_FACTORS


def test_evaluate_is_deterministic():
    """FR-002 / SC-004."""
    kwargs = dict(age=23, policy_types=["Auto"], claims=[_claim(4000, "Denied")], claims_ratio=4.06)
    first = rules.evaluate(**kwargs)
    second = rules.evaluate(**kwargs)
    assert [(r.factor, r.points, r.band_label) for r in first] == [
        (r.factor, r.points, r.band_label) for r in second
    ]


def test_evaluate_total_never_exceeds_max_score():
    """FR-005: the scale cannot be blown out by any accepted input."""
    results = rules.evaluate(
        age=18, policy_types=["Auto"], claims=[_claim(999999, "Denied")], claims_ratio=155.1
    )
    assert sum(r.points for r in results) <= rules.max_score()


# ---------------------------------------------------------------------------
# Defensive paths (T097; 100% coverage on rules.py, Principle V's
# business-rule core).
#
# Each of these guards a condition the current schema already forbids at
# the ORM layer (Customer.age is non-nullable; PolicyType.choices is
# exactly the four ranked types; the DB's risk_score_range constraint
# keeps score in 0-100). rules.py is a pure module with no ORM access by
# design (module docstring, point 1), so it cannot lean on the schema to
# rule these inputs out -- the guards exist because a caller from a REPL,
# a future factor, or a schema change could still reach them. 100%
# coverage means proving each one, not deleting it as unreachable.
# ---------------------------------------------------------------------------


def test_score_age_is_not_evaluable_when_age_is_none():
    """
    Defensive: Customer.age is non-nullable, so this path is unreachable
    through the ORM today -- but score_age() takes a plain Optional[int],
    not a Customer, and must handle the absence honestly if ever called
    with one (FR-018).
    """
    result = rules.score_age(None)
    assert result.status == rules.FactorStatus.NOT_EVALUABLE
    assert result.points == 0
    assert result.unevaluable_reason


def test_score_policy_type_is_not_evaluable_for_an_unranked_type():
    """
    Defensive: PolicyType.choices is exactly the four names in
    POLICY_TYPE_POINTS today, so this path is unreachable through the ORM
    -- but score_policy_type() takes plain strings and must not silently
    score an unranked coverage type as if it were evaluated (FR-018).
    """
    result = rules.score_policy_type(["Umbrella"])
    assert result.status == rules.FactorStatus.NOT_EVALUABLE
    assert result.points == 0
    assert result.unevaluable_reason


def test_select_raises_on_a_value_outside_every_band():
    """
    Defensive: every band table in this module starts at 0 and ends at
    infinity, so `_select` cannot fail for a caller that has already
    established a non-negative input -- this proves the fallthrough is a
    real programming-error guard, not dead code, by actually triggering
    it with a negative value.
    """
    with pytest.raises(ValueError, match="no band contains"):
        rules._select(rules.AGE_BANDS, -1)


def test_tier_for_raises_outside_the_stated_scale():
    """
    Defensive: the risk_score_range DB constraint keeps a stored score in
    0-100, so this path is unreachable for any persisted assessment --
    but tier_for() takes a plain int and must refuse a value the tier
    table was never built to cover (FR-006, FR-007).
    """
    with pytest.raises(ValueError, match="falls outside"):
        rules.tier_for(101)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _claim(amount, status="Approved"):
    """A minimal claim stand-in. rules.py must not require ORM objects."""
    return rules.ClaimInput(amount=amount, status=status)
