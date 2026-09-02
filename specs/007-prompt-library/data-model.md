# Data Model: Prompt Library (Phase 4a)

**Feature**: `007-prompt-library` | **Date**: 2026-09-02

**This feature adds no database table and no migration.** Everything below is
an in-memory structure defined in `apps/prompts/library.py` and
`apps/prompts/bindings.py`. The only database-visible effect of the whole
feature is additional rows in the existing `audit_auditlog` table, written
through the existing refusal path in `apps/core/exception_handlers.py`.

This mirrors `apps/risk/rules.py`, which likewise defines its business content
as plain frozen values with no Django import, so it can be exercised without a
database.

---

## 1. `EligibleRecordType` — the whitelist

A module-level frozenset of strings in `bindings.py`, the enforcement point for
FR-023/FR-024.

```
ELIGIBLE_RECORD_TYPES = frozenset({
    "Customer", "Policy", "Claim", "RiskAssessment", "RiskFactor",
})
```

Strings, not model classes, so `bindings.py` stays Django-free. `validation.py`
resolves each name to its real model via the app registry when checking field
existence.

**Pinned by exact equality in both directions**, mirroring
`apps/risk/tests/test_rules.py:270`. A subset check would admit a sixth type;
a superset check would let one be silently dropped. The test's docstring must
state that a failure means amending FR-023 deliberately — never relaxing the
assertion.

**Permanently excluded** (FR-025), and each one a genuinely-existing field that
field-existence checking alone would admit:

| Excluded type | Real fields it would expose | Source |
|---|---|---|
| `User` | `password` (credential hash), `is_superuser`, `role` | `apps/accounts/models.py:19-23` — `AbstractBaseUser, PermissionsMixin` |
| `AuditLog` | `before`, `after` — prior-state snapshots of *other* records | `apps/audit/models.py:35-36` |
| Any future type | — | Added only by deliberate amendment in its own module's spec |

`AuditLog.before`/`after` is the case that makes the whitelist load-bearing
rather than tidy: those JSONFields hold arbitrary prior state of arbitrary
records, so a single approved declaration against them re-exposes every field of
every record type — including the excluded ones — through one entry that passes
every other check.

---

## 2. `FieldBinding` — one declared field

Frozen dataclass. One entry in a template's declaration.

| Field | Type | Meaning |
|---|---|---|
| `record_type` | `str` | Must be in `ELIGIBLE_RECORD_TYPES` (FR-023) |
| `field_name` | `str` | Must exist on that model (FR-006) |
| `placeholder` | `str` | The exact token in the body: `{Customer.name}` |

Validation rules (all in `validation.py`, all enforced for the whole library at
app-ready):

- **FR-023**: `record_type in ELIGIBLE_RECORD_TYPES`, else reject naming the type.
- **FR-006**: `field_name` resolves on that model via `_meta.get_field()`, else
  reject naming the field. This catches a future rename or removal (spec edge
  case) at startup rather than at generation time.
- **FR-005**: the set of bindings equals the set of placeholders extracted from
  the body — equality, not containment, in both directions. An undeclared
  reference and an unused declaration are both rejections.
- **FR-021**: whether the binding names a personally-identifying field or a
  protected characteristic is a recorded per-template decision (see §3's
  `pii_note`). No Phase 4a template declares `Customer.gender` (`research.md` §3).

---

## 3. `PromptTemplate` — one template

Frozen dataclass. Seven instances in `library.py`.

| Field | Type | Meaning | Requirement |
|---|---|---|---|
| `identifier` | `str` | Stable, unique across library, e.g. `risk_assessment_summary` | FR-001 |
| `purpose` | `str` | What output, for which audience | FR-002 |
| `body` | `str` | Prompt text with `{RecordType.field_name}` placeholders | FR-003 |
| `bindings` | `tuple[FieldBinding, ...]` | The grounding contract | FR-004, FR-020 |
| `version` | `str` | Semver, per-template, e.g. `"1.0.0"` | FR-009 |
| `model_preference` | `ModelPreference` | Phase 0's finding, as data | FR-018 |
| `phase0_origin` | `str \| None` | Phase 0 template name this derives from | FR-016 |
| `phase0_divergence` | `str \| None` | How it differs from what Phase 0 validated | FR-016, `research.md` §2 |
| `pii_note` | `str` | Recorded decision about PII/protected characteristics | FR-021 |

`bindings` is a tuple, not a list, so a template is hashable and cannot be
mutated after definition — the same instinct behind `rules.py`'s frozen bands.

**`phase0_divergence` is not decoration.** Five of the seven templates are
rewrites (`research.md` §2), and their provenance must say so rather than imply
an untouched port. The recorded Phase 0 *model* finding stays valid across a
text rewrite — it was a finding about `llama3.1:8b`, not about one string — but
the text did change, and the record should not obscure that.

---

## 4. `ModelPreference` — Phase 0's finding as data

Frozen dataclass. FR-018's requirement that the finding survive as data rather
than only as prose in a runbook.

| Field | Type | Value |
|---|---|---|
| `preferred` | `str` | `"llama3.1:8b"` |
| `disqualified` | `tuple[tuple[str, str], ...]` | `(("phi3:mini", "hallucinated specific data fields (claim IDs, policy numbers) — disqualifying for an insurance/compliance context regardless of speed"),)` |

Both values verified against `~/insurance-ai-platform-phase0/readme-setup-conclusions.md:121-124`
(`research.md` §1). The disqualification reason is carried close to verbatim
because the *reason* is the reusable part — a future model evaluation should be
able to read what disqualified `phi3:mini` and test the replacement against the
same failure mode.

---

## 5. The library and its version

```
TEMPLATES: tuple[PromptTemplate, ...]      # the 7
PROMPT_LIBRARY_VERSION: str = "1.0.0"      # library-wide
```

`PROMPT_LIBRARY_VERSION` follows `apps/risk/rules.py:85`'s `RULE_SET_VERSION`
convention exactly — a semver string constant, changed deliberately.

**FR-010 enforcement — version bound to content.** A constant alone cannot
detect a body edited without a version bump, so a test hashes each template's
`body + bindings` and compares against a checked-in expected digest per
template. Editing either without bumping the version fails the suite with a
message naming the template. This is the same enforcement instinct as the risk
module's factor-set equality test: state the invariant as an assertion that
fails loudly rather than a convention people must remember.

`RULE_SET_VERSION` is stamped onto every assessment (`engine.py:72`) so a stored
score names the rules that produced it. The analogous obligation — stamping
`version` onto every generated output — belongs to Phase 4b, which produces the
outputs. The field exists here so 4b has it to stamp.

---

## 6. The seven templates

Identifiers, Phase 0 origin, and eligible record types drawn on. Per
`research.md` §2, the five marked *rewritten* drop a `{Client_Feedback}`
reference that maps to no platform field.

| # | `identifier` | Phase 0 origin | Status | Record types drawn on |
|---|---|---|---|---|
| 1 | `risk_assessment_summary` | Risk Assessment Summary | clean port* | Customer, Policy, Claim, RiskAssessment |
| 2 | `fraud_high_risk_flag_summary` | Fraud / High-Risk Flag Summary | rewritten | Customer, Policy, Claim, RiskAssessment |
| 3 | `personalized_renewal_reminder` | Personalized Renewal Reminder | rewritten | Customer, Policy |
| 4 | `cross_sell_recommendation` | Cross-Sell Recommendation | rewritten | Customer, Policy, RiskAssessment |
| 5 | `claim_summary_internal` | Claim Summary (internal) | rewritten | Customer, Policy, Claim, RiskAssessment |
| 6 | `behavioral_pattern_analysis` | Behavioral Pattern Analysis | **rewritten** | Customer, Policy, Claim, RiskAssessment |
| 7 | `executive_summary` | Executive Summary (leadership review) | as-is | Customer, Policy, Claim, RiskAssessment |

*Corrected during implementation.* This table originally listed rows 1 and 6
the other way round. Verified directly against
`~/insurance-ai-platform-phase0/app.py`: the five templates whose Phase 0
source referenced `{Client_Feedback}` are rows **2, 3, 4, 5 and 6** — Risk
Assessment Summary is **not** among them. Row 1 still carries a
`phase0_divergence`, but for a different reason: Phase 0's flat `{Risk_Score}`
column had to be rebound to the authoritative `RiskAssessment.score` rather
than `Customer.risk_score`'s denormalized mirror. Row 7 is the only template
with `phase0_divergence = None`.

`test_rewritten_templates_record_their_divergence` pins the corrected set.

`RiskFactor` is eligible but drawn on by no template as shipped. That is
correct and deliberate — it is the natural source for a per-factor narrative
("your score is elevated because ..."), which is Phase 4b/Module 10 territory.
The whitelist's exact-equality pin (§1) means an unused eligible type cannot be
silently dropped from the approved set just because nothing currently uses it.

**Field-name translation.** Phase 0's placeholders are CSV column names
(`{Client_Name}`, `{Policy_Premium_USD}`); the library's are qualified model
fields (`{Customer.name}`, `{Policy.premium_usd}`). The full column-to-field
map, including the two unmappable columns, is `research.md` §2.

**A note on `Risk_Score`.** Phase 0's `{Risk_Score}` maps to
`RiskAssessment.score` (0–90 integer, `rules.py:66-72`), *not* to
`Customer.risk_score`, which is a denormalized `score / 100` mirror explicitly
documented as "not a second source of truth"
(`apps/customers/models.py:122-131`). Templates declare the authoritative field.

---

## 7. Relationship to existing entities

This feature **reads model field definitions** — `_meta.get_field()` — to
validate declarations. It reads no row, writes no row, and adds no field to any
existing model.

| Entity | Relationship |
|---|---|
| `Customer`, `Policy`, `Claim`, `RiskAssessment`, `RiskFactor` | Field *definitions* consulted at validation time. Data untouched. |
| `AuditLog` | Receives refusal rows via the existing handler. Append-only, unchanged. Also permanently ineligible as a binding target (§1). |
| `User` | Supplies `request.user.role` for `HasRole`. Permanently ineligible as a binding target (§1). |
| `AuditedRoute` | One new entry registered in `register_defaults()`. The four existing entries are untouched (FR-014, SC-006). |
