# Research: Prompt Library (Phase 4a)

**Feature**: `007-prompt-library` | **Date**: 2026-09-02

This document resolves the four open items the spec left for planning: the
Phase 0 reconciliation flagged as a live item in the spec's Assumptions and
`checklists/requirements.md` note 3, plus the three deliberately-deferred
scope decisions (role sets, placeholder syntax, renderer scope) from note 4.

---

## §1. Phase 0 reconciliation — the count is 7, not 18

**The spec's Assumptions recorded 18 templates as taken-as-given and unverifiable
from this repository. That is now resolved: the artifacts exist and the number
is wrong.**

The Phase 0 repository was not missing — it is at `~/insurance-ai-platform-phase0`,
outside this project's working directory, which is why the original spec pass
could not see it. Read directly:

| Claim (from the feature description) | Verified? | Evidence |
|---|---|---|
| 18 verified templates | **NO — it is 7** | `app.py:43-101` defines exactly 7 keys in `PROMPT_TEMPLATES`; `readme-setup-conclusions.md:192` states "All 7 prompt templates tested against `llama3.1:8b`" and §9's results table lists 8 runs across those 7 templates (Risk Assessment Summary run twice) |
| `llama3.1:8b`, no hallucinations observed | **YES** | `readme-setup-conclusions.md:264` — "8/8 saved runs rated 👍"; §9 table shows 👍 for every template |
| `phi3:mini` disqualified for hallucinating claim IDs / policy numbers | **YES, verbatim** | `readme-setup-conclusions.md:121-124` — "it hallucinates specific data fields (claim IDs, policy numbers) — disqualifying for an insurance/compliance context regardless of speed" |

**Decision**: FR-016 and FR-018 are satisfied against **7** Phase 0 templates.
The spec's Assumptions bullet and FR-016 need the count corrected; the two model
findings stand exactly as written and need no change.

**Rationale**: The spec explicitly named FR-016/FR-018 as "what needs revising"
if reconciliation turned up different numbers. It did. Correcting the count now
is cheaper than discovering it during `/speckit-implement`, when a task saying
"port 18 templates" would have no 18th template to port.

**Alternatives considered**: Treating 18 as the target and authoring 11 net-new
templates to reach it. Rejected — those 11 would have no Phase 0 validation
behind them, which is precisely what FR-016/FR-018 exist to record. A template
nobody ran against a model is not a "verified template," and inventing them to
hit a remembered number would put unvalidated content behind a requirement whose
entire purpose is provenance.

The 7 templates, with their Phase 0 names:

1. Risk Assessment Summary
2. Fraud / High-Risk Flag Summary
3. Personalized Renewal Reminder
4. Cross-Sell Recommendation
5. Claim Summary (internal)
6. Behavioral Pattern Analysis
7. Executive Summary (leadership review)

**Latency note carried forward for 4b, not actionable here**:
`readme-setup-conclusions.md` §9 measured 42.0s–119.8s, average 84.4s per
generation on CPU-only inference (no GPU passthrough in WSL2). The BRD's
"<10 second AI response" NFR is unreachable on this hardware by roughly 4-12x.
This is 4b's problem (it argues for async generation via the Celery
infrastructure Phase 3b already built), and is recorded here only so 4b's plan
does not have to rediscover it.

---

## §2. Field mapping — 5 of 7 templates cannot be ported as written

This is the most consequential finding, and it is what FR-017 was written to
catch. Mapping every Phase 0 CSV column against the platform's actual model
fields:

| Phase 0 CSV column | Platform field | Status |
|---|---|---|
| `Client_ID` | `Customer.client_id` | ok |
| `Client_Name` | `Customer.name` | ok |
| `Client_Email` | `Customer.email` | ok |
| `Client_Phone` | `Customer.phone` | ok |
| `Client_Age` | `Customer.age` | ok |
| `Client_Gender` | `Customer.gender` | ok (but see §3) |
| `Client_Location` | `Customer.location` | ok |
| `Policy_Type` | `Policy.policy_type` | ok |
| `Policy_Start_Date` | `Policy.start_date` | ok |
| `Policy_End_Date` | `Policy.end_date` | ok |
| `Policy_Premium_USD` | `Policy.premium_usd` | ok |
| `Claim_Status` | `Claim.claim_status` | ok |
| `Claim_Amount_USD` | `Claim.claim_amount_usd` | ok |
| `Risk_Score` | `RiskAssessment.score` | ok |
| `Renewal_Probability` | `Policy.renewal_probability` | ok |
| `Fraud_Risk_Flag` | `Customer.fraud_risk_flag` | ok |
| `Cross_Sell_Score` | `Customer.cross_sell_score` | ok |
| `Lead_Source` | `Customer.lead_source` | ok |
| `Last_Interaction` | — | **UNMAPPABLE — no such field anywhere** |
| `Client_Feedback` | — | **UNMAPPABLE — no such field anywhere** |

`Client_Feedback` appears in **5 of the 7** templates (verified: 5 occurrences
in `app.py`). Under FR-006 (declared fields must exist) and FR-017 (no template
admitted with an unhonorable declaration), those five cannot be ported verbatim.

**Decision**: Port all 7 templates, but **rewrite the five that reference
`Client_Feedback` to drop that reference**, rather than deferring them. Record
each rewrite explicitly as a Phase 0 divergence in the template's own metadata.
`Last_Interaction` is referenced by none of the 7 and needs no handling.

**Rationale**: Deferring 5 of 7 would leave a 2-template library, which fails
FR-016's coverage intent for no good reason. Every one of the five templates
retains a coherent purpose without the feedback line — "summarize this
customer's risk profile" does not depend on free-text feedback; the feedback
sentence was Phase 0 flavor drawn from a CSV column the production schema never
adopted. The alternative — admitting them with a `Client_Feedback` declaration
— is exactly the unhonorable declaration FR-017 forbids, and would hand 4b's
validator a field it can never resolve.

**Alternatives considered**:
- *Add a `feedback` field to `Customer` to preserve the templates verbatim.*
  Rejected firmly. Phase 4a's spec says it "does not add to, modify, or read the
  data in" the business record types (Key Entities). Adding a column to a core
  model to accommodate a prompt inverts the dependency — templates must be
  grounded in the data the platform has, never the reverse. That is the whole
  premise of the grounding contract.
- *Defer all five under FR-016.* Rejected as disproportionate, per above.

**Consequence for FR-018's model-preference metadata**: a rewritten template is
no longer byte-identical to what Phase 0 validated. Its recorded provenance must
say so — "derived from Phase 0's *Behavioral Pattern Analysis*, feedback
reference removed (no platform field)" — rather than implying an untouched port.
Honesty here matters more than a clean-looking lineage: the recorded finding is
about the *model*, which the rewrite does not invalidate, but the template text
did change and the record should not obscure that.

---

## §3. The eligible-record-type whitelist and its interaction with `gender`

FR-023/FR-024/FR-025 fix the whitelist at exactly five types: `Customer`,
`Policy`, `Claim`, `RiskAssessment`, `RiskFactor`.

**Decision**: Enforce with a module-level frozenset pinned by an exact-equality
test, directly mirroring `apps/risk/tests/test_rules.py:270`
(`test_factor_set_is_exactly_the_approved_five`) — equality in both directions,
with a docstring stating that a failure means amending FR-023 deliberately, not
relaxing the assertion.

**Rationale**: The risk module already proved this pattern works for exactly
this problem — a set that prose alone failed to protect. `rules.py:44` records
why: without the assertion, FR-017 "lives only in prose ... and nothing fails
when someone adds a `gender` band." The prompt library's whitelist had precisely
that weakness before FR-023 (it was prose in Key Entities and Assumptions), which
is what the spec review caught.

**Verified attack surface this closes** — every one of these is a genuinely
existing field that FR-004–008 alone would have admitted:

| Declaration | Why it passes field-existence | Why it must be rejected |
|---|---|---|
| `User.password` | `apps/accounts/models.py:19` — `User(AbstractBaseUser, PermissionsMixin)`, so `password` is a real inherited field | It is a credential hash |
| `User.is_superuser` | Real, inherited from `PermissionsMixin` | Authorization state, not business data |
| `User.role` | `apps/accounts/models.py:23` | Authorization state |
| `AuditLog.before` / `.after` | `apps/audit/models.py:35-36`, real JSONFields | **The sharpest case** — these hold prior-state snapshots of *other* records, so one approved declaration re-exposes arbitrary fields of arbitrary types, including ineligible ones. A full bypass of the contract through a single validating entry. |

**On `Customer.gender`** (spec edge case + FR-021): it is an eligible field on
an eligible type, so the whitelist does not exclude it — and one Phase 0
template (*Cross-Sell Recommendation*) does not use it while others reference
location and age. The risk module deliberately excluded gender as a *scoring
factor* for regulatory exposure (`rules.py:40-47`), but that is a different
question from whether a narrative may mention it.

**Decision**: No Phase 4a template declares `Customer.gender`. None of the 7
Phase 0 templates reference it (verified — `Client_Gender` appears in the CSV
but in none of the 7 template strings), so this costs nothing today and is
recorded per-template under FR-021 as a deliberate exclusion rather than an
accident of what Phase 0 happened to write.

**Rationale**: Consistency with the platform's existing posture. Having
deliberately kept a protected characteristic out of the scoring path, admitting
it into the generated-narrative path without a stated reason would undo that
choice by inattention. If a future template genuinely needs it, FR-021 requires
that to be an explicit recorded decision.

---

## §4. Role sets — the fifth distinct shape

The spec deferred exact role sets, noting each existing registry entry chose its
own deliberately. Existing shapes, read from source:

| Module | View roles | Write roles | Source |
|---|---|---|---|
| Customer | 7 | 2 (Customer Service, Sysadmin) | `audit_routes.py:106-115` |
| Policy | 8 | 2 (Underwriter, Sysadmin) | `audit_routes.py:128-140` |
| Claim | 5 | 2 (Claims Adjuster, Sysadmin) | `audit_routes.py:161-172` |
| Risk | 5 | 2 (Risk Manager, Sysadmin) | `audit_routes.py:191-200` |
| Audit log itself | 2 (Compliance Officer, Sysadmin) | — | `apps/audit/views.py:19` |

**Decision**: **View = all 9 roles. Write = System Administrator alone (1 role).**

This is a genuinely new shape in both halves — the first universal view set, and
the first single-role write set (every existing module pairs a business role with
Sysadmin).

**Rationale**:
- *View is universal* because a prompt template contains **no customer data**.
  It is configuration describing what a future narrative may say — the field
  *names* it may draw on, never any field *values*. Every restriction in the
  four existing entries protects an individual's data; there is no individual
  here to protect. Restricting reads would be cargo-culting the shape of the
  other modules without their reason. Executive Leadership — excluded from all
  four existing view sets — can read prompt templates, which is the concrete
  proof this set was reasoned about rather than copied.
- *Write is Sysadmin alone* because prompt templates are administrative
  configuration (BRD Module 12 lists them beside Users, Roles, Permissions). No
  business role owns them the way Underwriters own policy terms. There is no
  second role with a defensible claim, so pairing one in for symmetry would be
  inventing an owner.

**Alternatives considered**: Copying Risk's 5-role view set, since the flagship
template is the risk narrative. Rejected — that set exists because a risk
assessment is a judgment about a person (`audit_routes.py:188-190`). A template
is a judgment about nobody. Reusing the number without the reason is what
FR-013's "own role sets" language exists to prevent.

**Note on write routes in Phase 4a**: the library is code-resident (§6), so
there may be no write route at all in this phase. The write role set is
registered regardless, because `audit_routes.roles_for()` consults it for any
write-method refusal — a POST to a read-only route must still be classified
correctly.

---

## §5. Placeholder syntax

**Decision**: `{RecordType.field_name}` — e.g. `{Customer.name}`,
`{RiskAssessment.tier}`, `{Policy.premium_usd}`. Parsed with a single regex;
each placeholder names its record type and field explicitly.

**Rationale**: The declaration must be derivable from the body and checkable
against it (FR-005, both directions). A qualified placeholder makes the body
self-describing — `{Customer.name}` states its own record type, so validation is
a set comparison between what the regex extracts and what the declaration lists,
with no inference step that could disagree. A bare `{name}` would require a
resolution rule ("which record type owns `name`?") that is ambiguous the moment
two eligible types share a field name — and three of the five already do
(`archived_at` on Customer/Policy/Claim, `customer` on Policy/RiskAssessment).

**Alternatives considered**:
- *Phase 0's bare `{Client_Name}` + `str.format(**row)`.* Rejected. It carries
  format specs (`{Policy_Premium_USD:,.2f}`) that complicate parsing, its names
  are CSV columns rather than model fields, and `str.format` on a flat dict
  cannot express which record a field came from. Phase 0 was a spike over one
  denormalized CSV row; the platform has five related models.
- *Jinja2 / Django templates.* Rejected — a full template language admits
  conditionals, loops, and filters, which makes "every placeholder binds to
  exactly one declared field" (FR-007) undecidable by static inspection. The
  contract is only enforceable if the body's data references are a flat,
  statically-extractable set. This is a case where a less capable mechanism is
  the correct one.

**Consequence**: a literal `{` in prompt text needs an escape. `{{` / `}}`,
following `str.format` convention. None of the 7 templates contains a literal
brace, so this is defensive.

---

## §6. Library residence and renderer scope

**Decision (residence)**: templates live in a Python module,
`apps/prompts/library.py`, as frozen dataclasses — not database rows. Confirms
the spec's Assumption rather than revisiting it.

**Rationale**: FR-008 requires whole-library validation that fails loudly and
completely. Code-resident templates validate at app-ready (the same hook
`audit_routes.register_defaults()` already uses, `apps/core/apps.py:8-15`), so a
malformed library fails at startup — the loudest available failure. Database rows
would be validated at write time, leaving a window where the library on disk is
valid and the library in the database is not, and would make a template change
invisible to code review. BRD Module 12's eventual runtime editing is a later
concern; when it arrives, this validation logic is what it will call.

**Decision (renderer)**: Phase 4a ships **binding and validation, but no
rendering**. The library exposes each template's body, its declared bindings, and
a resolver that turns a `(RecordType, field_name)` declaration into a concrete
value from a supplied record set — but nothing that substitutes values into the
body to produce a finished prompt string.

**Rationale**: FR-019 forbids model calls, not string formatting, so a renderer
would not violate the letter of the spec. But a rendered prompt has exactly one
consumer — the LLM service in 4b — and building it here means designing it
against a service that does not exist yet. The resolver is the genuinely
reusable half (4b's post-generation validator needs *values by declared field*
to check generated text field-by-field, which is the resolver's output, not the
renderer's). Splitting at the resolver boundary gives 4b both halves of what it
needs and leaves the half that depends on 4b's design to 4b.

**Alternatives considered**: shipping an inert renderer for testability.
Rejected — the resolver is independently testable without it, and a renderer
built now would likely be rewritten in 4b once the actual prompt-assembly needs
(system prompts, few-shot examples, output-format instructions) are known.

---

## §7. Success auditing — a real divergence, resolved narrowly

**Finding**: FR-015 says "every access to the prompt library — successful or
refused — MUST be recorded." Verified against the codebase: **no module in this
platform audits successful reads.**

- `apps/risk/views.py` contains **zero** `record_action` calls. Risk audits
  computation (`engine.py:142`, `tasks.py:34`), not viewing.
- Customers/policies/claims audit `create`/`update`/`destroy` only
  (`customers/views.py:102,131,151` and equivalents).
- Refusals are audited automatically and centrally for all modules, via
  `apps/core/exception_handlers.py:90`.

So the audit trail's current invariant is: **writes and refusals are recorded;
successful reads are not.** Implementing FR-015 literally would make the prompt
library the only module writing an audit row per GET — a row per list and per
detail request, on a table the platform treats as an append-only compliance
record.

**Decision**: Implement FR-015 as **refusals audited (automatic, via the
registry entry) + writes audited (if any write route exists)**, matching the
existing platform-wide invariant exactly. Do **not** audit successful reads.
Amend FR-015's wording to say so.

**Rationale**: The divergence is in the spec, not the codebase. FR-013/FR-014's
whole point is that the registry gains a fifth consumer *behaving like the other
four* — and SC-006 requires the existing four to be unaffected. A prompt library
that alone logs successful reads would not be the registry's fifth consumer; it
would be a fifth consumer plus a new platform convention, introduced silently in
a phase whose spec says RBAC and audit logging "reuse existing mechanisms."

There is also a substantive reason, not merely a consistency one: a successful
read of a prompt template discloses no customer data (§4). The compliance value
of the audit trail is in recording who touched *personal data* and who was
*refused*. Logging every template list would add volume without adding
compliance signal.

**Alternatives considered**: implementing FR-015 literally and accepting the
divergence. Rejected — but flagged as the one place this plan knowingly narrows
a written requirement, so it is called out in plan.md's Complexity Tracking
rather than buried here. If the intent really is to audit reads, that is a
platform-wide change belonging in its own spec, applied to all five modules at
once.

---

## §8. Version constant convention

**Decision**: Each template carries its own `version` string field; the module
additionally exposes `PROMPT_LIBRARY_VERSION` for the library as a whole.
Per-template versions are pinned against content by a test that hashes body +
declared bindings and compares to a checked-in expected value per template.

**Rationale**: FR-009 requires the existing `RULE_SET_VERSION` convention
(`apps/risk/rules.py:85` — a semver string constant, changed deliberately) and
FR-010 requires detecting a content change unaccompanied by a version change.
A constant alone cannot detect that; something must bind version to content.
Hashing gives FR-010 its enforcement, and follows the same instinct as the risk
module's factor-set equality test: state the invariant as an assertion that
fails loudly, not as a convention people are asked to remember.

`RULE_SET_VERSION` is stamped onto every assessment (`engine.py:72`) so a stored
score names the rules that produced it. The analogous obligation — stamping the
template version onto every generated output — falls to 4b, since 4a produces no
output. The field exists here so 4b has it to stamp.

---

## Summary of decisions

| # | Decision | Spec impact |
|---|---|---|
| 1 | Phase 0 has **7** templates, not 18; both model findings confirmed | **FR-016 + Assumptions need the count corrected** |
| 2 | Port all 7; rewrite 5 to drop `Client_Feedback` (no platform field); record divergence per template | Within FR-016/FR-017 as written |
| 3 | Whitelist = 5 types, frozenset + exact-equality test mirroring the risk factor-set test; no template declares `gender` | Implements FR-023/FR-024/FR-025, FR-021 |
| 4 | View = all 9 roles; Write = Sysadmin alone | Implements FR-012/FR-013 |
| 5 | `{RecordType.field_name}` placeholders, regex-extracted | Implements FR-007 |
| 6 | Code-resident library, validated at app-ready; resolver but **no renderer** | Confirms Assumptions; scopes FR-019/FR-020 |
| 7 | Audit refusals + writes, **not successful reads** — matches platform invariant | **FR-015 needs narrowing** |
| 8 | Per-template version + content hash test | Implements FR-009/FR-010 |

Two items (1 and 7) require spec amendments and are carried into plan.md's
Complexity Tracking rather than being applied silently.
