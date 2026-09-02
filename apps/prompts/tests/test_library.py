"""
Library content, versioning and Phase 0 provenance (T029-T034 US2,
T052-T061 US4).

The version tests are the ones with teeth. FR-009 asks each template to carry
a semver string, which a constant satisfies trivially -- but FR-010 asks that
a version CHANGE whenever content changes, and no constant can enforce that
about itself. `test_template_content_matches_its_version` binds the two by
hashing, so an edited body with a stale version fails the suite by name.

The provenance tests exist because this library's content came from a spike
whose findings live in a runbook nothing checks. Carrying "llama3.1:8b, phi3
disqualified" as data (FR-018) is only worth something if something asserts
it stayed true.
"""
import hashlib

import pytest

from apps.prompts import library

SEMVER = __import__("re").compile(r"^\d+\.\d+\.\d+$")


# ---------------------------------------------------------------------------
# T029-T031 (US2) -- versioning
# ---------------------------------------------------------------------------


def test_library_version_is_semver():
    assert SEMVER.match(library.PROMPT_LIBRARY_VERSION)


@pytest.mark.parametrize("template", library.TEMPLATES, ids=lambda t: t.identifier)
def test_every_template_has_a_semver_version(template):
    """FR-009. Same convention as apps/risk/rules.py:85's RULE_SET_VERSION."""
    assert SEMVER.match(template.version)


def test_versions_are_independent_per_template():
    """
    FR-009 / US2 acceptance scenario 3. Each template carries its own
    `version` field rather than deriving it from PROMPT_LIBRARY_VERSION, so
    revising one template does not silently restamp the other six.

    Asserted structurally -- the field exists per instance and is a plain
    string, not a property reading the module constant.
    """
    for t in library.TEMPLATES:
        assert "version" in t.__dataclass_fields__
        assert isinstance(t.__dict__["version"], str)


def _content_digest(template):
    """
    A stable hash of exactly what FR-010 protects: the body and the declared
    bindings. Deliberately EXCLUDES version, purpose, provenance and pii_note
    -- editing a docstring-ish field is not a contract change and should not
    force a version bump, while editing the body or the declaration is and
    must.
    """
    parts = [template.body]
    for b in sorted(template.bindings, key=lambda b: (b.record_type, b.field_name)):
        parts.append(f"{b.record_type}.{b.field_name}={b.placeholder}")
    return hashlib.sha256("\x00".join(parts).encode()).hexdigest()[:16]


# Checked-in expected digests, one per template. Regenerate a value ONLY when
# deliberately changing that template's body or bindings -- and bump its
# `version` in the same edit. That pairing is the whole point.
EXPECTED_DIGESTS = {
    "risk_assessment_summary": "1b7fa0f8f4f4b5aa",
    "fraud_high_risk_flag_summary": "29dc854d2dc68471",
    "personalized_renewal_reminder": "ebc9f9bdba058ef2",
    "cross_sell_recommendation": "1fb98b346ac36e82",
    "claim_summary_internal": "f87fffd5573bdbe1",
    "behavioral_pattern_analysis": "b7d80e14cc7326e5",
    "executive_summary": "91af33e3e102d448",
}


@pytest.mark.parametrize("template", library.TEMPLATES, ids=lambda t: t.identifier)
def test_template_content_matches_its_version(template):
    """
    FR-010's only enforcement point.

    A version constant cannot detect a body edited beneath it -- so this test
    pins content to an expected digest. If it fails, ONE of two things is
    true and you must pick deliberately:

      - you changed the body or bindings on purpose: bump this template's
        `version` AND update its digest below, in the same commit;
      - you changed them by accident: revert.

    Do not update the digest alone. That is exactly the drift FR-010 exists
    to prevent -- one version denoting two different template contents.
    """
    assert _content_digest(template) == EXPECTED_DIGESTS[template.identifier], (
        f"content of {template.identifier!r} changed without a matching "
        f"version bump (FR-010). Either bump its version and update the "
        f"digest, or revert the content edit."
    )


# ---------------------------------------------------------------------------
# T052-T061 (US4) -- Phase 0 coverage and provenance
# ---------------------------------------------------------------------------

PHASE0_TEMPLATE_NAMES = {
    "Risk Assessment Summary",
    "Fraud / High-Risk Flag Summary",
    "Personalized Renewal Reminder",
    "Cross-Sell Recommendation",
    "Claim Summary (internal)",
    "Behavioral Pattern Analysis",
    "Executive Summary (leadership review)",
}

EXPECTED_IDENTIFIERS = {
    "risk_assessment_summary",
    "fraud_high_risk_flag_summary",
    "personalized_renewal_reminder",
    "cross_sell_recommendation",
    "claim_summary_internal",
    "behavioral_pattern_analysis",
    "executive_summary",
}


def test_library_has_exactly_seven_templates():
    """
    FR-016 enforcement point. EQUALITY, both directions.

    THE COUNT IS SEVEN, NOT EIGHTEEN. The feature description asked for
    "Phase 0's 18 already-verified templates"; the Phase 0 artifacts define
    seven, and were read directly during planning:

      - ~/insurance-ai-platform-phase0/app.py:43-101 -- exactly 7 keys
      - readme-setup-conclusions.md:192 -- "All 7 prompt templates tested
        against llama3.1:8b"

    FR-016 forbids adding a template merely to reach a count: a template
    nobody ran against a model is not a "verified template", and inventing
    eleven to hit a remembered number would put unvalidated content behind the
    very requirement that exists to record provenance.

    If this fails because someone added an eighth, delete the eighth -- do not
    relax the assertion.
    """
    identifiers = {t.identifier for t in library.TEMPLATES}
    assert identifiers == EXPECTED_IDENTIFIERS
    assert len(library.TEMPLATES) == 7


@pytest.mark.parametrize("template", library.TEMPLATES, ids=lambda t: t.identifier)
def test_every_template_traces_to_a_phase0_origin(template):
    """FR-016. No template appears from nowhere."""
    assert template.phase0_origin in PHASE0_TEMPLATE_NAMES


def test_no_phase0_prompt_type_was_deferred():
    """
    FR-016 / SC-007. Every Phase 0 prompt type is accounted for -- present,
    not silently dropped.

    FR-016's defer path is satisfied VACUOUSLY here: research.md §2
    determined all seven are portable (five needing a Client_Feedback
    rewrite), so DEFERRED_PHASE0_TYPES is empty by construction.

    That constant exists rather than being omitted so a future deferral has
    somewhere to live -- and this test is what fails until one is recorded
    there. If a template ever becomes unportable, adding it to
    DEFERRED_PHASE0_TYPES with a reason is what makes this pass again.
    """
    origins = {t.phase0_origin for t in library.TEMPLATES}
    deferred = {name for name, _reason in library.DEFERRED_PHASE0_TYPES}

    assert origins | deferred == PHASE0_TEMPLATE_NAMES, (
        "a Phase 0 prompt type is neither present in the library nor recorded "
        "as deferred (FR-016/SC-007)."
    )
    assert library.DEFERRED_PHASE0_TYPES == ()
    for _name, reason in library.DEFERRED_PHASE0_TYPES:
        assert reason, "a deferral must carry a stated reason (FR-016)"


# The five whose Phase 0 source referenced {Client_Feedback}, verified
# directly against ~/insurance-ai-platform-phase0/app.py. Note that Risk
# Assessment Summary is NOT among them -- it and Executive Summary are the
# two clean ports on that axis.
PHASE0_FEEDBACK_DEPENDENT = {
    "fraud_high_risk_flag_summary",
    "personalized_renewal_reminder",
    "cross_sell_recommendation",
    "claim_summary_internal",
    "behavioral_pattern_analysis",
}


@pytest.mark.parametrize("template", library.TEMPLATES, ids=lambda t: t.identifier)
def test_rewritten_templates_record_their_divergence(template):
    """
    FR-016 / research.md §2. Provenance must not imply an untouched port.

    Every template whose Phase 0 source used Client_Feedback MUST say so --
    the recorded model finding still holds across a rewrite (it was a finding
    about llama3.1:8b, not about one string), but the text did change and the
    record should not obscure that.
    """
    if template.identifier in PHASE0_FEEDBACK_DEPENDENT:
        assert template.phase0_divergence, (
            f"{template.identifier} was rewritten to drop Client_Feedback but "
            f"records no divergence"
        )
        assert "Client_Feedback" in template.phase0_divergence


_FORBIDDEN_FIELD_NAMES = {
    "feedback",
    "client_feedback",
    "last_interaction",
    "lastinteraction",
}


@pytest.mark.parametrize("template", library.TEMPLATES, ids=lambda t: t.identifier)
def test_no_template_declares_an_unmappable_phase0_column(template):
    """
    FR-017. Client_Feedback and Last_Interaction are Phase 0 CSV columns with
    no corresponding field anywhere in the platform. A declaration naming one
    is exactly the unhonorable declaration FR-017 forbids -- it would hand
    Phase 4b's validator a field it can never resolve.

    (Validation would already reject these via FR-006, since the field does
    not exist. This asserts the intent directly, so the reason is legible.)
    """
    for b in template.bindings:
        assert b.field_name.lower() not in _FORBIDDEN_FIELD_NAMES


@pytest.mark.parametrize("template", library.TEMPLATES, ids=lambda t: t.identifier)
def test_model_preference_records_phase0_findings(template):
    """
    FR-018. The finding survives as data, not only as prose in a runbook.

    Verified against readme-setup-conclusions.md:121-124 and :264.
    """
    assert template.model_preference.preferred == "llama3.1:8b"

    disqualified = dict(template.model_preference.disqualified)
    assert "phi3:mini" in disqualified

    reason = disqualified["phi3:mini"].lower()
    assert "claim id" in reason
    assert "policy number" in reason


@pytest.mark.parametrize("template", library.TEMPLATES, ids=lambda t: t.identifier)
def test_no_template_declares_gender(template):
    """
    FR-021. Customer.gender is an eligible field on an eligible type -- the
    whitelist does not exclude it, so nothing structural stops a template
    declaring it. This does.

    The risk module deliberately excluded gender as a scoring factor for
    regulatory exposure (apps/risk/rules.py:40-47). Whether a narrative may
    MENTION it is a different question from whether a score may be COMPUTED
    from it -- but having kept a protected characteristic out of the scoring
    path, admitting it into the generated-narrative path without a stated
    reason would undo that choice by inattention.

    None of the seven Phase 0 templates referenced it, so this costs nothing
    today. If a future template genuinely needs it, FR-021 requires that be an
    explicit recorded decision -- amend this test deliberately.
    """
    for b in template.bindings:
        assert not (b.record_type == "Customer" and b.field_name == "gender")


@pytest.mark.parametrize("template", library.TEMPLATES, ids=lambda t: t.identifier)
def test_every_template_records_a_pii_decision(template):
    """FR-021. The decision is recorded per template, never implicit."""
    assert template.pii_note
    assert len(template.pii_note) > 40


@pytest.mark.parametrize("template", library.TEMPLATES, ids=lambda t: t.identifier)
def test_every_template_has_a_meaningful_purpose(template):
    """
    FR-002. Non-empty is the floor, not the requirement.

    The identifier-restatement check is what makes this more than an
    emptiness assertion: a `purpose` of "risk assessment summary" on
    `risk_assessment_summary` would satisfy FR-002's letter and none of its
    intent. A purpose must say what output it produces and for whom.
    """
    assert template.purpose
    normalized_purpose = template.purpose.lower().strip().rstrip(".")
    normalized_identifier = template.identifier.replace("_", " ")
    assert normalized_purpose != normalized_identifier
    assert len(template.purpose) > 60, (
        f"{template.identifier}'s purpose is too thin to name both an output "
        f"and an audience"
    )


@pytest.mark.parametrize("template", library.TEMPLATES, ids=lambda t: t.identifier)
def test_risk_score_binds_to_the_authoritative_field(template):
    """
    Phase 0's flat {Risk_Score} column has two possible homes in the
    platform, and only one is correct.

    RiskAssessment.score is the 0-90 authoritative value
    (apps/risk/rules.py:66-72). Customer.risk_score is a denormalized
    score/100 mirror written only by the engine and documented in
    apps/customers/models.py:122-131 as "not as a second source of truth".

    A template binding the mirror would produce narratives citing a number
    that can lag the assessment it describes.
    """
    for b in template.bindings:
        assert not (b.record_type == "Customer" and b.field_name == "risk_score")
