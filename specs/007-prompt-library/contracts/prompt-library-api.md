# Contract: Prompt Library API

**Feature**: 007-prompt-library | **Base path**: `/api/prompts/`

Mounted at a **top-level prefix**, matching the reasoning that put risk at
`/api/risk/` rather than nesting it (see `specs/005-risk-scoring-engine/research.md`
§1). A nested path would fall under an existing registry entry and mis-audit
every prompt refusal against the wrong module's role set. There is no plausible
parent here anyway — a template belongs to no customer.

Auth: session or token per the platform default. All routes require
authentication.

**Read-only in Phase 4a.** The library is code-resident (`research.md` §6), so
no route creates, updates, or deletes a template. Write roles are nonetheless
registered (see below) because `audit_routes.roles_for()` consults them to
classify any write-method refusal.

## Roles

The fifth distinct role shape on the platform, and a genuinely new one in both
halves — the first universal view set, and the first single-role write set.

| Role | Read templates | Write |
|---|---|---|
| Risk Manager | ✅ | ❌ |
| System Administrator | ✅ | ✅ |
| Underwriter | ✅ | ❌ |
| Fraud Analyst | ✅ | ❌ |
| Compliance Officer | ✅ | ❌ |
| Claims Adjuster | ✅ | ❌ |
| Customer Service | ✅ | ❌ |
| Product Manager | ✅ | ❌ |
| Executive Leadership | ✅ | ❌ |

**Nine read roles, one write role** (`research.md` §4). Compare the four
existing entries: Customer 7/2, Policy 8/2, Claim 5/2, Risk 5/2.

*Why universal read*: a prompt template contains **no customer data**. It
carries the field *names* a future narrative may draw on, never any field
*values*. Every restriction in the four existing entries protects an
individual's data; there is no individual here to protect. Executive
Leadership — excluded from all four existing view sets — can read prompt
templates, which is the concrete proof this set was reasoned about rather than
copied from a neighbouring module.

*Why Sysadmin alone for write*: prompt templates are administrative
configuration (BRD Module 12 lists them beside Users, Roles, Permissions). No
business role owns them the way an Underwriter owns policy terms, so pairing
one in for symmetry with the other four entries would be inventing an owner.

---

## `GET /api/prompts/templates/`

List every template. Not paginated — the library is 7 items and fixed at
deploy time, so pagination would add a page envelope around a response that can
never grow at runtime.

Serves from the in-memory tuple. **Executes zero database queries.**

**200 response**

```json
{
  "library_version": "1.0.0",
  "count": 7,
  "results": [
    {
      "identifier": "risk_assessment_summary",
      "purpose": "Underwriting-facing narrative summarising a customer's risk profile and the factors behind it.",
      "version": "1.0.0",
      "model_preference": {
        "preferred": "llama3.1:8b",
        "disqualified": [
          {
            "model": "phi3:mini",
            "reason": "hallucinated specific data fields (claim IDs, policy numbers) — disqualifying for an insurance/compliance context regardless of speed"
          }
        ]
      },
      "phase0_origin": "Risk Assessment Summary",
      "phase0_divergence": "Client_Feedback reference removed — no corresponding platform field.",
      "pii_note": "Draws on name and age; declares no protected characteristic. Customer.gender deliberately excluded.",
      "bindings": [
        {"record_type": "Customer", "field_name": "name", "placeholder": "{Customer.name}"},
        {"record_type": "Customer", "field_name": "age", "placeholder": "{Customer.age}"},
        {"record_type": "Policy", "field_name": "policy_type", "placeholder": "{Policy.policy_type}"},
        {"record_type": "Policy", "field_name": "premium_usd", "placeholder": "{Policy.premium_usd}"},
        {"record_type": "Claim", "field_name": "claim_status", "placeholder": "{Claim.claim_status}"},
        {"record_type": "RiskAssessment", "field_name": "score", "placeholder": "{RiskAssessment.score}"},
        {"record_type": "RiskAssessment", "field_name": "tier", "placeholder": "{RiskAssessment.tier}"}
      ]
    }
  ]
}
```

The list route includes `bindings` — FR-011 requires the declared field list on
the list route specifically, so the grounding contract is readable without
fetching each template individually. `body` is detail-only.

**403** for an unauthenticated caller. No role produces a 403 here, since all
nine may read; the refusal path is exercised only by unauthenticated requests
and by write methods.

---

## `GET /api/prompts/templates/{identifier}/`

One template in full, including `body`.

Lookup is by `identifier` (the stable slug), not by a numeric pk — there is no
table and therefore no pk. `lookup_field = "identifier"`, which `HasRole`
already handles: its `_is_detail_route()` reads `lookup_url_kwarg or
lookup_field` from `view.kwargs` (`apps/core/permissions.py:42-44`), so
existence non-disclosure works unchanged on a non-pk lookup.

**200 response** — every field from the list response, plus:

```json
{
  "identifier": "risk_assessment_summary",
  "body": "Summarize {Customer.name}'s risk profile. They are {Customer.age} years old and hold a {Policy.policy_type} policy with a premium of {Policy.premium_usd}. Their most recent claim status is {Claim.claim_status}. Their computed risk score is {RiskAssessment.score} ({RiskAssessment.tier} tier). Write a 3-line underwriting comment on their risk status.",
  "…": "all list fields"
}
```

Every `{...}` token in `body` appears in `bindings`, and every entry in
`bindings` appears in `body` — FR-005, enforced at app-ready for the whole
library, so a response can never carry a body and declaration that disagree.

**404** for an unknown identifier (ordinary miss for a permitted role), and
**404** for an unauthenticated caller (existence non-disclosure via
`has_object_permission`). Both shapes are already produced by `HasRole`; this
module adds no new refusal behavior.

---

## Audit behavior

The module's `audit_routes` entry — FR-013's "fifth consumer", registered in
`register_defaults()` alongside the existing four:

| Property | Value |
|---|---|
| `prefix` | `/api/prompts/` |
| `target_type` | `prompts.PromptTemplate` |
| `action_prefix` | `prompt` |
| `view_roles` | all 9 |
| `write_roles` | `(SYSTEM_ADMINISTRATOR,)` |

Resulting action names, from `audit_routes.action_for()`'s existing suffix map:
`prompt.viewed`, `prompt.created`, `prompt.updated`, `prompt.deleted`.

**What is recorded**: refusals, automatically, via
`apps/core/exception_handlers.py` — no per-module code. Nothing else, because
this phase has no write route.

**What is deliberately not recorded**: successful reads. No module on this
platform audits successful reads (verified — `apps/risk/views.py` has zero
`record_action` calls; customers/policies/claims audit create/update/destroy
only). This narrows FR-015's literal wording, and the reasoning is
`research.md` §7 plus plan.md's Complexity Tracking: the prompt library must
behave *as the registry's fifth consumer*, and a successful template read
discloses no customer data.

Since all nine roles may read, the refusal rows this module produces in practice
come from unauthenticated requests and from write-method attempts — the latter
being exactly why `write_roles` is registered on a read-only module.
