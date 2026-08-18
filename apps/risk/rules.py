"""
The rule set: five factors, four tiers, one declarative table (T012).

This module is the single source of truth for scoring (FR-003). The same
structure that computes a score produces the labels the explanation reads
in, so the computation and the explanation cannot disagree about what the
rules are. There is no second table to drift.

Four properties are structural here rather than policed by convention:

1. NO DJANGO IMPORT. Not the ORM, not settings, not TextChoices. The rules
   are pure functions over plain values, which is what lets test_rules.py
   exercise every band boundary without a database. `engine.py` owns the
   translation from ORM objects to the primitives below; keeping that
   boundary means a scoring bug is reproducible from a REPL with no
   fixtures. `ClaimInput` exists for exactly this reason -- the rules take
   a claim-shaped value, never a `Claim` row.

2. THE BANDS ARE DATA, NOT BRANCHES. Each factor is a tuple of bands and
   each band carries its bounds, its label and its points together. A
   band cannot acquire a label that disagrees with the value that selected
   it, because one lookup returns both. `max_score()` sums the table
   rather than restating 100, so a point value cannot be edited without
   the scale following it.

3. ONE BOUNDARY CONVENTION, ENCODED ONCE. Every band is
   `lower <= value < upper`, lower-inclusive and upper-exclusive, with the
   top band closed by an infinite upper bound (FR-007). Age exactly 25 is
   `25-34`, never `under 25` -- the edge case the spec raises. Tier
   thresholds follow the same rule, so 20 is Moderate and 19 is Low. The
   convention lives in `_select` and nowhere else; no factor reimplements
   its own comparison.

4. UNKNOWN IS NOT ZERO (FR-018). A factor whose data is absent returns
   NOT_EVALUABLE with a reason, not a zero-point band. Two of the five
   factors need a live policy, and scoring a customer without one as zero
   would assert their coverage carries no additional risk -- a claim about
   data the system does not have.

FR-017: the factor set is exactly the five in `FACTORS`. Gender, location,
lead_source and fraud_risk_flag were each measured against the seeded 3,000
rows and rejected as near-uniform (research.md §5); gender is additionally a
protected characteristic whose use in risk scoring carries regulatory
exposure. `test_factor_set_is_exactly_the_approved_five` pins this by exact
equality in both directions -- adding a sixth factor or dropping one of these
five fails the suite by design. If that test fails, amend FR-017
deliberately; do not relax the assertion.

Point values and tier thresholds were validated against all 3,000 seeded
customers before adoption (research.md §5): every tier clears SC-005's 5%
floor, and the observed range is 0-90 of a possible 90 -- the top of the
scale is reachable and was reached.

THE SCALE IS 0-90, NOT 0-100. `max_score()` sums the table below and returns
90. The 0-100 figures in data-model.md and plan.md are the storage envelope
-- the `risk_score_range` DB constraint and the `score / 100` mirror -- which
is an outer bound a 0-90 rule set satisfies, not a target it must reach.
`TIER_BANDS` likewise runs its top band to 100 to match that constraint;
scores in 91-100 are unreachable under this rule set. FR-005 requires a
stated scale with a defined maximum, and does not name 100.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Optional, Sequence, Union

# FR-004. Changes when the factors, bands, point values or tier thresholds
# change -- and is stamped onto every assessment (FR-026) so a stored score
# always names the rules that produced it. Assessments computed under an
# older version stay readable and are not silently reinterpreted.
RULE_SET_VERSION = "1.0.0"

Number = Union[int, float, Decimal]


class FactorStatus:
    """
    Mirrors `models.FactorStatus` by value, without importing it.

    Deliberate duplication: `models.py` needs Django TextChoices for the
    column, this module must stay import-free (see docstring note 1). The
    two are kept in step by `test_factor_status_values_match_the_model`
    over in the model tests -- string equality, asserted, rather than a
    shared import that would drag the ORM in here.
    """

    EVALUATED = "evaluated"
    NOT_EVALUABLE = "not_evaluable"


# ---------------------------------------------------------------------------
# Inputs and outputs -- plain values, no ORM
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ClaimInput:
    """
    A claim reduced to the two fields the rules actually read.

    `engine.py` builds these from live `Claim` rows. Frozen because a rule
    must never mutate its input: determinism (FR-002) is easier to hold
    when the inputs cannot be edited mid-evaluation.
    """

    amount: Number
    status: str


@dataclass(frozen=True)
class FactorResult:
    """
    One factor's contribution -- and the whole of its explanation.

    The fields map one-to-one onto `RiskFactor` columns, so `persist()`
    writes a factor row without deciding anything: what the customer's
    value was, which band it fell into, what that band contributed
    (FR-020). `points` is 0 for a zero-contribution band and 0 for a
    not-evaluable factor; `status` is what separates them (FR-022,
    FR-023).
    """

    factor: str
    status: str
    observed_value: str
    band_label: str
    points: int
    unevaluable_reason: str = ""


@dataclass(frozen=True)
class Band:
    """
    One band of one factor: its bounds, its label and its points together.

    Bounds are `lower <= value < upper`. The top band of every factor
    carries `upper=math.inf`, which is what "closed at the top" means
    mechanically -- no band needs a special case to catch the maximum.
    """

    lower: float
    upper: float
    label: str
    points: int


# ---------------------------------------------------------------------------
# The table -- computation and explanation, one structure (FR-003)
# ---------------------------------------------------------------------------

# FR-009. Under-25 and 65+ carry the load; the middle bands are 0 because
# they are the reference population, not because they are unevaluated.
AGE_BANDS: tuple[Band, ...] = (
    Band(0, 25, "under 25", 15),
    Band(25, 35, "25-34", 5),
    Band(35, 50, "35-49", 0),
    Band(50, 65, "50-64", 0),
    Band(65, math.inf, "65 and over", 10),
)

# FR-010. Keyed by coverage type rather than banded on a number -- the only
# categorical factor in the set. Order is by descending points because
# `score_policy_type` reads it as a preference order (FR-008).
POLICY_TYPE_POINTS: tuple[tuple[str, int], ...] = (
    ("Auto", 15),
    ("Health", 10),
    ("Property", 5),
    ("Life", 0),
)

# FR-011, FR-013. Three outcomes, deliberately distinct. 1,143 of the 2,246
# seeded claims are exactly 0.00 -- an event that occurred and cost nothing.
# Collapsing it into either neighbour would misdescribe half the claiming
# population, so it gets its own band between them.
CLAIMS_NONE = Band(0, 1, "no claim", 0)
CLAIMS_ZERO_AMOUNT = Band(1, 2, "zero-amount claim only", 5)
CLAIMS_NON_ZERO = Band(2, math.inf, "one or more non-zero claims", 20)
CLAIMS_HISTORY_BANDS: tuple[Band, ...] = (
    CLAIMS_NONE,
    CLAIMS_ZERO_AMOUNT,
    CLAIMS_NON_ZERO,
)

# FR-012. The top band is what bounds the factor: the seeded maximum ratio
# is 155x premium, and it contributes exactly 30 -- the same as 5x. Without
# a closed top band one extreme ratio would dominate the whole score.
CLAIMS_RATIO_BANDS: tuple[Band, ...] = (
    Band(0, 1, "under 1x premium", 0),
    Band(1, 3, "1-3x premium", 10),
    Band(3, 5, "3-5x premium", 20),
    Band(5, math.inf, "5x premium and over", 30),
)

# FR-014. Scored on the presence of a denial, independently of claims
# history -- a denied claim of 0.00 contributes here AND lands in the
# zero-amount history band. The two factors describe different things and
# must not be entangled.
DENIED_CLAIM_BANDS: tuple[Band, ...] = (
    Band(0, 1, "no denied claim", 0),
    Band(1, math.inf, "denied claim present", 10),
)

DENIED_STATUS = "Denied"

# FR-006, FR-007. Lower-inclusive, upper-inclusive as written here (the
# ranges are stated closed on both sides because they are integers), with
# no gap and no overlap across 0-100. The tier is derived from the score
# and never assigned independently.
#
# The top band runs to 100 rather than to the reachable maximum of 90, to
# match the `risk_score_range` DB constraint in data-model.md (0 <= score
# <= 100). Scores of 91-100 are unreachable under rule set 1.0.0 -- the
# table sums to 90 -- so the extra headroom is inert, not a gap. Deliberate:
# it keeps one stated range across the tier table and the column constraint,
# and means a future point-value rise cannot push a score past the tiers
# before anyone notices. `tier_for` covers the whole 0-100 range either way.
TIER_BANDS: tuple[tuple[str, int, int], ...] = (
    ("low", 0, 19),
    ("moderate", 20, 39),
    ("elevated", 40, 59),
    ("high", 60, 100),
)

# FR-017's enforcement surface. The order is the order factors appear in an
# explanation: the customer's own characteristic first, then their cover,
# then their history. `evaluate()` returns one result per entry, always.
FACTORS: tuple[str, ...] = (
    "age",
    "policy_type",
    "claims_history",
    "claims_ratio",
    "denied_claim",
)

# Per-factor maxima, read off the table rather than restated, so `max_score`
# cannot fall out of step with a point value someone edits above.
_FACTOR_MAXIMA: dict[str, int] = {
    "age": max(b.points for b in AGE_BANDS),
    "policy_type": max(p for _, p in POLICY_TYPE_POINTS),
    "claims_history": max(b.points for b in CLAIMS_HISTORY_BANDS),
    "claims_ratio": max(b.points for b in CLAIMS_RATIO_BANDS),
    "denied_claim": max(b.points for b in DENIED_CLAIM_BANDS),
}


# ---------------------------------------------------------------------------
# The one boundary convention (FR-007)
# ---------------------------------------------------------------------------


def _select(bands: Sequence[Band], value: float) -> Band:
    """
    Return the band containing `value` under `lower <= value < upper`.

    Every banded factor routes through here, which is what makes the
    convention true once rather than five times. The fallthrough is a
    programming error, not a data condition: the tables above start at 0
    and end at infinity, so a value can only escape them by being
    negative -- and every caller has already established its input is not.
    """
    for band in bands:
        if band.lower <= value < band.upper:
            return band
    raise ValueError(f"no band contains {value!r} -- the band table has a gap")


def _evaluated(factor: str, observed: str, band: Band) -> FactorResult:
    return FactorResult(
        factor=factor,
        status=FactorStatus.EVALUATED,
        observed_value=observed,
        band_label=band.label,
        points=band.points,
    )


def _not_evaluable(factor: str, reason: str) -> FactorResult:
    """
    FR-018. Points are 0 because there is nothing to add, but the status
    says why -- the reason is what stops a reader treating this as an
    assessed absence of risk. The DB constraint
    `factor_reason_matches_status` refuses a not-evaluable row without one.
    """
    return FactorResult(
        factor=factor,
        status=FactorStatus.NOT_EVALUABLE,
        observed_value="",
        band_label="not evaluable",
        points=0,
        unevaluable_reason=reason,
    )


# ---------------------------------------------------------------------------
# The five factors
# ---------------------------------------------------------------------------


def score_age(age: Optional[int]) -> FactorResult:
    """
    FR-009. Age is derived by the caller from date of birth; this function
    bands an integer and nothing else.

    Absent age is not evaluable rather than zero (FR-018) -- though in the
    seeded data every customer carries a date of birth, so this path is
    defensive rather than routine.
    """
    if age is None:
        return _not_evaluable("age", "Customer has no recorded date of birth")
    return _evaluated("age", str(age), _select(AGE_BANDS, age))


def score_policy_type(policy_types: Iterable[str]) -> FactorResult:
    """
    FR-010, FR-008. The HIGHEST-SCORING live policy type wins.

    The seeded export carries exactly one policy per customer (verified:
    `policies_per_customer = 1` for all 3,000), but the model permits many,
    so the combination rule is stated here rather than left to the shape of
    one export. Worst-case for coverage type: a customer holding Life and
    Auto is scored on Auto, because the Auto exposure is real regardless of
    what else they hold.

    A customer with no live policy is NOT EVALUABLE (FR-016, FR-018).
    Archived policies never reach this function -- the caller filters to
    live rows -- so "no live policy" and "no policy" are the same condition
    here.
    """
    types = list(policy_types)
    if not types:
        return _not_evaluable(
            "policy_type", "Customer holds no live policy"
        )

    ranking = {name: points for name, points in POLICY_TYPE_POINTS}
    known = [t for t in types if t in ranking]
    if not known:
        return _not_evaluable(
            "policy_type",
            "Customer's policy coverage type is not in the rule set",
        )

    worst = max(known, key=lambda t: ranking[t])
    return _evaluated(
        "policy_type",
        worst,
        Band(0, math.inf, worst, ranking[worst]),
    )


def score_claims_history(claims: Sequence[ClaimInput]) -> FactorResult:
    """
    FR-011, FR-013. Three outcomes, and they must all differ.

    A claim of exactly 0.00 is an event that occurred and cost nothing. It
    is neither "no claim at all" nor "a claim of substance", and half the
    seeded claiming population sits in exactly that state. Mixed histories
    take the non-zero band: one real claim is not cancelled out by any
    number of zero-amount ones.

    Never not-evaluable -- an empty claim list is a fact about the
    customer, not missing data. That is the difference between this factor
    and `claims_ratio`, which needs a premium the customer may not have.
    """
    if not claims:
        band = CLAIMS_NONE
        observed = "no claims"
    elif any(_amount(c) > 0 for c in claims):
        band = CLAIMS_NON_ZERO
        observed = f"{sum(1 for c in claims if _amount(c) > 0)} non-zero claim(s)"
    else:
        band = CLAIMS_ZERO_AMOUNT
        observed = f"{len(claims)} zero-amount claim(s)"
    return _evaluated("claims_history", observed, band)


def score_claims_ratio(ratio: Optional[Number]) -> FactorResult:
    """
    FR-012. Total non-zero claimed amount over total live premium (FR-008),
    computed by the caller because it spans policies; banded here.

    The top band is the point of the factor: the seeded maximum is 155x
    premium and contributes exactly 30, the same as 5x. One extreme ratio
    therefore cannot dominate the total, which is FR-012's explicit
    requirement.

    A `None` ratio means there was no premium to divide by -- no live
    policy, or a premium of zero. That is not evaluable, not a ratio of
    zero (FR-018): a customer whose premium is unknown has not thereby
    demonstrated a favourable claims ratio.
    """
    if ratio is None:
        return _not_evaluable(
            "claims_ratio",
            "Customer has no live premium to compute a ratio against",
        )
    value = float(ratio)
    band = _select(CLAIMS_RATIO_BANDS, value)
    return _evaluated("claims_ratio", f"{value:.2f}", band)


def score_denied_claim(claims: Sequence[ClaimInput]) -> FactorResult:
    """
    FR-014. The presence of a denial, scored independently of history.

    A denied claim of 0.00 contributes 10 here and 5 in claims_history --
    the factors are not entangled, and the test suite pins that. Denial
    speaks to how the customer's claims have been assessed; history speaks
    to whether claims happened at all.
    """
    denied = sum(1 for c in claims if c.status == DENIED_STATUS)
    band = _select(DENIED_CLAIM_BANDS, denied)
    observed = f"{denied} denied claim(s)" if denied else "none denied"
    return _evaluated("denied_claim", observed, band)


# ---------------------------------------------------------------------------
# The scale and the tiers
# ---------------------------------------------------------------------------


def max_score() -> int:
    """
    FR-005. Summed from the table, never restated as a literal.

    15 + 15 + 20 + 30 + 10 = 90 under rule set 1.0.0. Editing any point
    value above moves this automatically, so the stated scale cannot drift
    from the bands that fill it.

    Returns 90, not 100 -- see the module docstring. This function summing
    the table rather than restating a literal is precisely what surfaced the
    discrepancy: the prose claimed 100 while the bands had always summed to
    90, and the code was right.
    """
    return sum(_FACTOR_MAXIMA[factor] for factor in FACTORS)


def tier_for(score: int) -> str:
    """
    FR-006, FR-007. Derived from the score alone -- no other input, so a
    stored tier can always be re-checked against its stored score.
    """
    for tier, lower, upper in TIER_BANDS:
        if lower <= score <= upper:
            return tier
    raise ValueError(
        f"score {score!r} falls outside 0-{max_score()} -- "
        "the tier table covers the whole scale, so this is a bad score"
    )


# ---------------------------------------------------------------------------
# The whole rule set, applied
# ---------------------------------------------------------------------------


def evaluate(
    *,
    age: Optional[int],
    policy_types: Iterable[str],
    claims: Sequence[ClaimInput],
    claims_ratio: Optional[Number],
) -> list[FactorResult]:
    """
    Evaluate every factor and return one result per factor, in `FACTORS`
    order -- always five, including zero contributions (FR-022) and
    not-evaluable ones (FR-023).

    Keyword-only: the four inputs are unrelated types and a positional call
    that silently swapped two of them would still produce a plausible
    score. Deterministic by construction (FR-002) -- pure functions over
    the arguments, no clock, no randomness, no query.

    The caller sums these for the score, and `persist()` writes the very
    results it summed. That is what makes FR-021's exact-sum guarantee
    structural rather than a coincidence tests must police.
    """
    results = [
        score_age(age),
        score_policy_type(policy_types),
        score_claims_history(claims),
        score_claims_ratio(claims_ratio),
        score_denied_claim(claims),
    ]
    # The order above is written out rather than dispatched through a dict
    # so it is readable, but FACTORS remains the authority on membership --
    # this asserts the two agree rather than trusting they do.
    assert [r.factor for r in results] == list(FACTORS), (
        "evaluate() and FACTORS disagree about the factor set"
    )
    return results


def _amount(claim: ClaimInput) -> float:
    """Claim amounts arrive as Decimal from the ORM and float from tests."""
    return float(claim.amount)
