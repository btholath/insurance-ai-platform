"""
The prompt library: seven versioned templates and their grounding contracts.

NO DJANGO IMPORT, for the reason `bindings.py` and `apps/risk/rules.py` give:
the library is plain frozen values, so its content is testable without a
database and reviewable in a diff. `validation.py` owns the ORM boundary.

SEVEN TEMPLATES, NOT EIGHTEEN. The feature description called for "Phase 0's
18 already-verified templates". The Phase 0 artifacts say otherwise, and were
read directly during planning (research.md §1):

  - `~/insurance-ai-platform-phase0/app.py:43-101` defines exactly 7 keys in
    PROMPT_TEMPLATES.
  - `readme-setup-conclusions.md:192` -- "All 7 prompt templates tested
    against llama3.1:8b".
  - §9's results table lists 8 runs across those 7 (Risk Assessment Summary
    run twice, on different clients).

Both MODEL findings from that spike were confirmed verbatim and are carried
into `ModelPreference` below, so they survive as data rather than as prose in
a runbook that nothing checks (FR-018).

FR-016 forbids adding a template merely to reach a count, and
`test_library_has_exactly_seven_templates` pins the set by exact equality.

FIVE OF THE SEVEN ARE REWRITES. Phase 0's CSV carried `Client_Feedback` and
`Last_Interaction`; the production schema adopted neither. Five templates
referenced `{Client_Feedback}`, so under FR-006/FR-017 they could not be
ported verbatim -- a declaration naming a field the platform does not have is
exactly the unhonorable declaration FR-017 forbids, and would hand Phase 4b's
validator something it can never resolve. Those five drop the reference and
say so in `phase0_divergence`, rather than implying an untouched port. The
recorded model finding still holds across a text rewrite -- it was a finding
about llama3.1:8b, not about one string -- but the text did change and the
record should not obscure it (research.md §2).
"""
from __future__ import annotations

from dataclasses import dataclass

from .bindings import FieldBinding

# FR-009. Follows `apps/risk/rules.py:85`'s RULE_SET_VERSION convention: a
# semver string constant, changed deliberately. Per-template versions live on
# each PromptTemplate; this names the library as a whole.
PROMPT_LIBRARY_VERSION = "1.0.0"


@dataclass(frozen=True)
class ModelPreference:
    """
    Phase 0's model evaluation, as data (FR-018).

    The disqualification REASON is carried close to verbatim because the
    reason is the reusable part: a future model evaluation should be able to
    read what disqualified phi3:mini and test its replacement against the same
    failure mode.
    """

    preferred: str
    disqualified: tuple  # ((model_name, reason), ...)


# Verified against ~/insurance-ai-platform-phase0/readme-setup-conclusions.md
# lines 121-124 and 264. Shared by every template: Phase 0 evaluated the
# models, not one prompt.
PHASE0_MODEL_PREFERENCE = ModelPreference(
    preferred="llama3.1:8b",
    disqualified=(
        (
            "phi3:mini",
            "hallucinated specific data fields (claim IDs, policy numbers) -- "
            "disqualifying for an insurance/compliance context regardless of "
            "speed",
        ),
    ),
)


@dataclass(frozen=True)
class PromptTemplate:
    """
    One named, versioned prompt and its grounding contract.

    `bindings` is a tuple rather than a list so a template is hashable and
    cannot be mutated after definition -- the same instinct behind the frozen
    bands in `apps/risk/rules.py`.
    """

    identifier: str
    purpose: str
    body: str
    bindings: tuple
    version: str
    model_preference: ModelPreference
    phase0_origin: str
    phase0_divergence: str | None
    pii_note: str


# FR-016's defer path. Empty by construction: research.md §2 determined all
# seven Phase 0 prompt types are portable (five with a Client_Feedback
# rewrite), so nothing was deferred.
#
# It exists rather than being omitted so the requirement has somewhere to
# live -- a deferral needs a home before it is needed, or the clause is
# unimplementable prose. Entries are (prompt_type, reason).
# `test_no_phase0_prompt_type_was_deferred` holds this honest.
DEFERRED_PHASE0_TYPES: tuple = ()


def _b(record_type, field_name):
    """A binding whose placeholder is derived from its own field, so the two
    cannot disagree -- the same 'one lookup returns both' instinct as the risk
    module's bands."""
    return FieldBinding(
        record_type, field_name, "{%s.%s}" % (record_type, field_name)
    )


RISK_ASSESSMENT_SUMMARY = PromptTemplate(
    identifier="risk_assessment_summary",
    purpose=(
        "Underwriting-facing narrative summarising a customer's risk profile "
        "and the factors behind it, for an Underwriter or Risk Manager "
        "reviewing whether a stored score is defensible."
    ),
    body=(
        "Summarize {Customer.name}'s risk profile. They are {Customer.age} "
        "years old and hold a {Policy.policy_type} policy with a premium of "
        "{Policy.premium_usd}. Their most recent claim status is "
        "{Claim.claim_status}. Their computed risk score is "
        "{RiskAssessment.score} ({RiskAssessment.tier} tier). Then write a "
        "3-line underwriting comment on their risk status."
    ),
    bindings=(
        _b("Customer", "name"),
        _b("Customer", "age"),
        _b("Policy", "policy_type"),
        _b("Policy", "premium_usd"),
        _b("Claim", "claim_status"),
        _b("RiskAssessment", "score"),
        _b("RiskAssessment", "tier"),
    ),
    version="1.0.0",
    model_preference=PHASE0_MODEL_PREFERENCE,
    phase0_origin="Risk Assessment Summary",
    # Phase 0's version of THIS template never referenced Client_Feedback
    # (verified against app.py) -- it is one of the two clean ports. The
    # divergence recorded here is the Risk_Score rebinding, which is real:
    # the CSV had one flat column, the platform has an authoritative
    # RiskAssessment.score plus a denormalized Customer.risk_score mirror,
    # and the template must name the authoritative one.
    phase0_divergence=(
        "Risk_Score now binds RiskAssessment.score (0-90, authoritative) "
        "rather than the CSV's flat column; Customer.risk_score is a "
        "score/100 mirror and explicitly not a second source of truth. "
        "No Client_Feedback reference existed in the Phase 0 original."
    ),
    pii_note=(
        "Draws on name and age. Declares no protected characteristic; "
        "Customer.gender deliberately excluded (FR-021)."
    ),
)


FRAUD_HIGH_RISK_FLAG_SUMMARY = PromptTemplate(
    identifier="fraud_high_risk_flag_summary",
    purpose=(
        "High-risk summary for a Fraud Analyst, surfacing the inconsistency "
        "between a low computed risk score and a High fraud flag."
    ),
    body=(
        "Generate a high-risk summary for {Customer.name}. Include their "
        "computed risk score {RiskAssessment.score} ({RiskAssessment.tier} "
        "tier), claim status {Claim.claim_status}, claim amount "
        "{Claim.claim_amount_usd}, renewal probability "
        "{Policy.renewal_probability}, and fraud risk flag "
        "{Customer.fraud_risk_flag}. If the risk score is low but the fraud "
        "flag is High, explicitly flag this as an inconsistency requiring "
        "fraud team review."
    ),
    bindings=(
        _b("Customer", "name"),
        _b("Customer", "fraud_risk_flag"),
        _b("Policy", "renewal_probability"),
        _b("Claim", "claim_status"),
        _b("Claim", "claim_amount_usd"),
        _b("RiskAssessment", "score"),
        _b("RiskAssessment", "tier"),
    ),
    version="1.0.0",
    model_preference=PHASE0_MODEL_PREFERENCE,
    phase0_origin="Fraud / High-Risk Flag Summary",
    phase0_divergence=(
        "Client_Feedback reference and its 'feedback tone' instruction "
        "removed -- no corresponding platform field."
    ),
    pii_note=(
        "Draws on name and fraud_risk_flag. No protected characteristic. "
        "fraud_risk_flag is stored-only data the platform does not yet "
        "compute (Phase 5 work); the template reports it, never derives it."
    ),
)


PERSONALIZED_RENEWAL_REMINDER = PromptTemplate(
    identifier="personalized_renewal_reminder",
    purpose=(
        "Customer-facing renewal reminder for Customer Service, framed as "
        "lapse prevention when renewal probability is low."
    ),
    body=(
        "Write a personalized {Policy.policy_type} insurance renewal reminder "
        "for {Customer.name}, age {Customer.age}, from {Customer.location}. "
        "Their premium is {Policy.premium_usd} and the policy ends "
        "{Policy.end_date}. Their renewal probability is "
        "{Policy.renewal_probability}. Keep the tone friendly and, if renewal "
        "probability is below 0.3, frame it as a lapse-prevention message "
        "instead of a routine reminder."
    ),
    bindings=(
        _b("Customer", "name"),
        _b("Customer", "age"),
        _b("Customer", "location"),
        _b("Policy", "policy_type"),
        _b("Policy", "premium_usd"),
        _b("Policy", "end_date"),
        _b("Policy", "renewal_probability"),
    ),
    version="1.0.0",
    model_preference=PHASE0_MODEL_PREFERENCE,
    phase0_origin="Personalized Renewal Reminder",
    phase0_divergence=(
        "Client_Feedback reference removed -- no corresponding platform "
        "field. Policy.end_date added so the reminder can name the date it "
        "is about, which the CSV version left implicit."
    ),
    pii_note=(
        "Draws on name, age and location -- all customer-facing detail the "
        "recipient already knows about themselves. No protected "
        "characteristic; Customer.gender deliberately excluded (FR-021)."
    ),
)


CROSS_SELL_RECOMMENDATION = PromptTemplate(
    identifier="cross_sell_recommendation",
    purpose=(
        "Cross-sell suggestion plus a short outreach email, for Customer "
        "Service or a Product Manager assessing product fit."
    ),
    body=(
        "Suggest the best policy type to cross-sell to {Customer.name}, age "
        "{Customer.age}, from {Customer.location}. They currently have a "
        "{Policy.policy_type} policy, a cross-sell score of "
        "{Customer.cross_sell_score}, a risk score of {RiskAssessment.score}, "
        "and a fraud flag of {Customer.fraud_risk_flag}. Then write a short "
        "personalized cross-sell email with a call to action."
    ),
    bindings=(
        _b("Customer", "name"),
        _b("Customer", "age"),
        _b("Customer", "location"),
        _b("Customer", "cross_sell_score"),
        _b("Customer", "fraud_risk_flag"),
        _b("Policy", "policy_type"),
        _b("RiskAssessment", "score"),
    ),
    version="1.0.0",
    model_preference=PHASE0_MODEL_PREFERENCE,
    phase0_origin="Cross-Sell Recommendation",
    phase0_divergence=(
        "Client_Feedback reference removed -- no corresponding platform field."
    ),
    pii_note=(
        "Draws on name, age and location. No protected characteristic -- "
        "notably Customer.gender is excluded, which matters more here than "
        "elsewhere: product recommendation is exactly the surface where a "
        "protected characteristic would be inappropriate (FR-021)."
    ),
)


CLAIM_SUMMARY_INTERNAL = PromptTemplate(
    identifier="claim_summary_internal",
    purpose=(
        "Structured internal claim summary for a Claims Adjuster's log -- "
        "never customer-facing."
    ),
    body=(
        "Create an internal claim summary for {Customer.name}, a "
        "{Customer.age}-year-old {Policy.policy_type} policyholder whose "
        "claim status is {Claim.claim_status} for {Claim.claim_amount_usd}. "
        "Include their risk score {RiskAssessment.score} "
        "({RiskAssessment.tier} tier), fraud flag "
        "{Customer.fraud_risk_flag}, and premium {Policy.premium_usd}. Format "
        "as a structured entry suitable for an internal log."
    ),
    bindings=(
        _b("Customer", "name"),
        _b("Customer", "age"),
        _b("Customer", "fraud_risk_flag"),
        _b("Policy", "policy_type"),
        _b("Policy", "premium_usd"),
        _b("Claim", "claim_status"),
        _b("Claim", "claim_amount_usd"),
        _b("RiskAssessment", "score"),
        _b("RiskAssessment", "tier"),
    ),
    version="1.0.0",
    model_preference=PHASE0_MODEL_PREFERENCE,
    phase0_origin="Claim Summary (internal)",
    phase0_divergence=(
        "Client_Feedback reference removed -- no corresponding platform field."
    ),
    pii_note=(
        "Draws on name and age, plus claim financials. Internal-only by "
        "purpose. No protected characteristic (FR-021)."
    ),
)


BEHAVIORAL_PATTERN_ANALYSIS = PromptTemplate(
    identifier="behavioral_pattern_analysis",
    purpose=(
        "Behavioral classification (churn risk / loyal / VIP / neutral) with "
        "stated reasoning, for a Product Manager or Risk Manager."
    ),
    body=(
        "Evaluate {Customer.name}'s behavioral pattern based on these data "
        "points: risk score {RiskAssessment.score} ({RiskAssessment.tier} "
        "tier), renewal probability {Policy.renewal_probability}, claim "
        "status {Claim.claim_status} for {Claim.claim_amount_usd}, and fraud "
        "flag {Customer.fraud_risk_flag}. Is this client a churn risk, loyal, "
        "VIP, or neutral? Explain the reasoning in 2-3 sentences."
    ),
    bindings=(
        _b("Customer", "name"),
        _b("Customer", "fraud_risk_flag"),
        _b("Policy", "renewal_probability"),
        _b("Claim", "claim_status"),
        _b("Claim", "claim_amount_usd"),
        _b("RiskAssessment", "score"),
        _b("RiskAssessment", "tier"),
    ),
    version="1.0.0",
    model_preference=PHASE0_MODEL_PREFERENCE,
    phase0_origin="Behavioral Pattern Analysis",
    phase0_divergence=(
        "Client_Feedback reference removed -- no corresponding platform "
        "field. This is the template that loses the most to that removal: "
        "Phase 0 fed the customer's own words into a churn/loyalty judgment. "
        "The remaining signals still support the classification, but a "
        "narrative built from them is reasoning from behaviour alone."
    ),
    pii_note=(
        "Draws on name only, plus behavioural signals. No protected "
        "characteristic -- deliberate, since behavioural classification is a "
        "judgment about a person and gender must not inform it (FR-021)."
    ),
)


EXECUTIVE_SUMMARY = PromptTemplate(
    identifier="executive_summary",
    purpose=(
        "Three-to-four sentence account summary for Executive Leadership, "
        "suitable for a dashboard tile."
    ),
    body=(
        "Write an executive summary paragraph of {Customer.name}'s account "
        "for leadership review. Include policy type {Policy.policy_type}, "
        "premium {Policy.premium_usd}, risk score {RiskAssessment.score} "
        "({RiskAssessment.tier} tier), renewal probability "
        "{Policy.renewal_probability}, and claim status "
        "{Claim.claim_status}. Keep it to 3-4 sentences, suitable for a "
        "dashboard summary."
    ),
    bindings=(
        _b("Customer", "name"),
        _b("Policy", "policy_type"),
        _b("Policy", "premium_usd"),
        _b("Policy", "renewal_probability"),
        _b("Claim", "claim_status"),
        _b("RiskAssessment", "score"),
        _b("RiskAssessment", "tier"),
    ),
    version="1.0.0",
    model_preference=PHASE0_MODEL_PREFERENCE,
    phase0_origin="Executive Summary (leadership review)",
    phase0_divergence=None,
    pii_note=(
        "Draws on name only, alongside policy and risk figures. No protected "
        "characteristic (FR-021)."
    ),
)


# FR-016. Exactly seven, pinned by
# `test_library_has_exactly_seven_templates`. Adding an eighth requires
# amending FR-016 and that test deliberately.
TEMPLATES = (
    RISK_ASSESSMENT_SUMMARY,
    FRAUD_HIGH_RISK_FLAG_SUMMARY,
    PERSONALIZED_RENEWAL_REMINDER,
    CROSS_SELL_RECOMMENDATION,
    CLAIM_SUMMARY_INTERNAL,
    BEHAVIORAL_PATTERN_ANALYSIS,
    EXECUTIVE_SUMMARY,
)
