# Runbook — Phase 4 (Prompt Library & LLM Services)

**Companion to `readme-runbook-phase1.md`** (Spec Kit methodology, the
beginner glossary, the full `/speckit-*` workflow explanation),
`readme-runbook-phase2.md` (the Core Domain phase) and
`readme-runbook-phase3.md` (the Risk Engine phase, including Celery's
introduction). This document assumes all three and focuses on what's
specific to Phase 4.

**Living document**, same convention as Phases 1-3 — sections marked
`⏳ PENDING` are placeholders, filled in with real content as each
sub-phase actually happens.

---

## 1. Scope and sequencing

| Sub-phase | Status | Depends on |
|---|---|---|
| **4a — Prompt Library (templates + data-binding contract)** | ✅ Complete | Phase 3a (RiskAssessment/RiskFactor exist to bind against) |
| **4b — LLM Service Integration + post-generation validator** | ⏳ PENDING | 4a |

Split for the same reason Phase 3 was: settle the contract that governs
what a generated narrative may say **before** wiring up anything that
generates. 4a ships inert configuration — templates are defined,
validated, versioned and served, but never executed. The whole of 4a
makes **zero language-model calls**, asserted in the test suite rather
than promised (`apps/prompts/tests/test_no_llm.py`).

The payoff is that 4b inherits a machine-checkable grounding contract
instead of having to invent one alongside the model integration.

---

## 2. What 4a actually built

One new app, `apps/prompts/`, with **no database table and no
migration**. Seven templates as frozen dataclasses in `library.py`,
validated as a unit at app-ready.

| File | Role |
|---|---|
| `bindings.py` | `FieldBinding`, the eligible-record-type whitelist, placeholder regex, the resolver. **Imports no Django** (same discipline as `apps/risk/rules.py`) |
| `validation.py` | Owns the ORM boundary; enforces the contract for the whole library |
| `library.py` | The seven templates, their versions and their Phase 0 provenance. Also Django-free |
| `views.py` / `serializers.py` / `urls.py` | Two read routes at `/api/prompts/templates/` |
| `apps.py` | `ready()` validates the library — a malformed template stops the process from starting |

**1246 tests passing** (1084 from Phase 3b + 162 new), **100% coverage
on every `apps/prompts/` file**.

---

## 3. The count was wrong: 7 templates, not 18

The feature description asked for "Phase 0's 18 already-verified
templates". **There are seven.**

The Phase 0 repository was never missing — it is at
`~/insurance-ai-platform-phase0`, outside this project's working
directory, which is why the `/speckit-specify` pass could not see it and
recorded the figure as unverifiable. `/speckit-plan` read it directly:

- `app.py:43-101` defines exactly 7 keys in `PROMPT_TEMPLATES`
- `readme-setup-conclusions.md:192` — "All 7 prompt templates tested
  against `llama3.1:8b`"
- §9's results table: 8 runs across those 7 (Risk Assessment Summary run
  twice, on different clients)

Both **model** findings were confirmed verbatim and are now carried as
data (`ModelPreference`), not just prose in a runbook:

- `llama3.1:8b` preferred — 8/8 runs rated usable
- `phi3:mini` disqualified — "hallucinated specific data fields (claim
  IDs, policy numbers) — disqualifying for an insurance/compliance
  context regardless of speed" (`readme-setup-conclusions.md:121-124`)

FR-016 was amended to seven **and** gained a clause forbidding padding
the library to reach a count. Authoring eleven net-new templates would
have put unvalidated content behind the very requirement that exists to
record provenance — a template nobody ran against a model is not a
"verified template".

`test_library_has_exactly_seven_templates` pins this by exact equality.

---

## 4. Five of seven couldn't be ported verbatim

Mapping every Phase 0 CSV column against real model fields turned up two
with no home anywhere in the platform:

- **`Client_Feedback`** — referenced by **5 of the 7 templates**
- **`Last_Interaction`** — referenced by none

Under FR-006 (declared fields must exist) and FR-017 (no unhonorable
declarations), those five could not be carried over as written. They
were **rewritten to drop the reference**, each recording the divergence
in its own `phase0_divergence` field so provenance never implies an
untouched port.

Two alternatives were rejected:

- *Add a `feedback` column to `Customer`.* This inverts the dependency
  the grounding contract exists to establish. Templates ground in the
  data the platform has; the platform does not grow columns to
  accommodate a prompt.
- *Defer all five.* Would leave a two-template library for no benefit.

**Which five, precisely** — verified against `app.py`, and worth stating
because the intuitive guess is wrong: Risk Assessment Summary is **not**
among them. It and Executive Summary are the two clean ports. The five
are Fraud/High-Risk, Renewal Reminder, Cross-Sell, Claim Summary and
Behavioral Pattern Analysis.

Behavioral Pattern Analysis loses the most: Phase 0 fed the customer's
own words into a churn/loyalty judgment. The remaining signals still
support the classification, but a narrative built from them reasons from
behaviour alone.

---

## 5. The whitelist — the finding that shaped the feature

The original spec validated that a declared field **exists** on the
record type it names, but never that the record type itself was
**approved**. The eligible-type list lived only as prose.

That gap was caught during spec review, and the exploit is worse than
theoretical. Every one of these is a genuinely existing field that
field-existence checking alone would have admitted:

| Declaration | Why it passes existence | Why it must be rejected |
|---|---|---|
| `User.password` | Real inherited field (`AbstractBaseUser`) | A credential hash |
| `User.is_superuser` | Real (`PermissionsMixin`) | Authorization state |
| `User.role` | `apps/accounts/models.py:23` | Authorization state |
| `AuditLog.before` / `.after` | Real JSONFields | **The sharpest case** |

`AuditLog.before`/`.after` hold prior-state snapshots of *other*
records. One approved declaration against them would re-expose arbitrary
fields of arbitrary record types — including the excluded ones — through
a single entry that passes every other check. A complete bypass of the
grounding contract.

Closed by FR-023/024/025 and enforced by a **frozenset pinned with
exact-equality in both directions**, mirroring
`apps/risk/tests/test_rules.py:270`'s factor-set test. A subset check
would admit a sixth type; a superset check would let one be silently
dropped.

**`test_ineligible_types_name_real_fields` is the load-bearing test** —
it asserts those fields genuinely resolve via `_meta.get_field()`, which
is what proves the whitelist rejects valid declarations rather than
typos. Without it the other two whitelist tests could pass while
rejecting nothing, and nobody would notice. That failure mode is not
hypothetical here: Phase 3b found a test that had asserted vacuously
across two phases.

---

## 6. FR-015 was narrowed, deliberately

The spec said "every access — successful or refused — MUST be recorded".
Verification found that **no module on this platform audits successful
reads**:

- `apps/risk/views.py` — zero `record_action` calls
- customers / policies / claims — create, update, destroy only
- refusals — audited centrally for all modules via
  `apps/core/exception_handlers.py`

Implementing the literal wording would have made the prompt library the
only module writing an audit row per GET, contradicting FR-013/FR-014's
premise that it behaves as the registry's **fifth consumer** and SC-006's
requirement that existing behaviour is unaffected. A template read also
discloses no customer data.

Narrowed to **refusals + writes**, recorded in the spec, `research.md`
§7, the plan's Complexity Tracking, and asserted by
`test_successful_read_writes_no_audit_row`. If auditing reads is ever
wanted, it is a platform-wide change for all five modules and belongs in
its own spec.

---

## 7. The fifth registry entry — a genuinely new role shape

| Module | View | Write |
|---|---|---|
| Customer | 7 | 2 (Customer Service, Sysadmin) |
| Policy | 8 | 2 (Underwriter, Sysadmin) |
| Claim | 5 | 2 (Claims Adjuster, Sysadmin) |
| Risk | 5 | 2 (Risk Manager, Sysadmin) |
| **Prompts** | **9** | **1 (Sysadmin)** |

First universal view set on the platform, and first single-role write
set. A prompt template holds field **names**, never field **values** —
it declares what a future narrative may draw on and discloses nothing
about any customer. The restrictions that make the other four sets
narrow have nothing to protect here.

**Executive Leadership returning 200 is the signal that matters.** It is
absent from all four existing view sets and present here; a 403 would
have meant the role set was copied from a neighbouring module rather
than chosen for this one.

Write is Sysadmin alone because prompt templates are administrative
configuration (BRD Module 12 lists them beside Users, Roles,
Permissions). No business role owns them the way an Underwriter owns
policy terms, so pairing one in for symmetry would invent an owner.
Phase 4a has **no write route at all** — the set is registered because
`roles_for()` consults it to classify a write-method refusal.

---

## 8. Scope boundaries held

- **No LLM call.** Asserted by source inspection in
  `test_no_llm.py`, not by mocking a client. Ollama is not even
  reachable from the web container.
- **No renderer.** 4a stops at the **resolver** (declaration → value),
  which is what 4b's post-generation validator actually needs. Rendering
  (values → finished prompt string) has exactly one consumer, and its
  shape depends on prompt-assembly decisions that do not exist yet.
  `test_no_renderer_exists` guards the boundary.
- **No new dependency.** Placeholder extraction is one `re` pattern from
  the standard library. A full template language was rejected because
  conditionals and loops would make "every placeholder binds to exactly
  one declared field" undecidable by static inspection.
- **No new table, no migration.**

---

## 9. Carried forward for 4b

- **Latency is the real problem.** Phase 0 measured **42.0s–119.8s per
  generation, averaging 84.4s** on CPU-only inference (no GPU
  passthrough in WSL2). The BRD's "<10 second AI response" NFR is
  unreachable on this hardware by roughly 4–12x. This argues for async
  generation over the Celery infrastructure Phase 3b already built.
- **The grounding contract is ready to consume.**
  `bindings.resolve(template, **records)` returns
  `{FieldBinding: value}` — exactly the field-by-field mapping a
  post-generation validator needs to check generated text against.
- **`RiskFactor` is eligible but unused.** It is the natural source for
  a per-factor narrative ("your score is elevated because…"), which is
  4b/Module 10 territory. The equality pin means it cannot fall out of
  the approved set just because nothing uses it yet.
- **Template versions exist to be stamped.** `RULE_SET_VERSION` is
  stamped onto every assessment (`engine.py:72`) so a stored score names
  the rules that produced it. The analogous obligation — stamping
  `template.version` onto every generated output — is 4b's, since 4a
  produces no output.

---

## 10. ⏳ PENDING — 4b (LLM Services + post-generation validator)

Filled in when 4b actually happens.
