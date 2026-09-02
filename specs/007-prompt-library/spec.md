# Feature Specification: Prompt Library

**Feature Branch**: `007-prompt-library`

**Created**: 2026-09-02

**Status**: Draft

**Input**: User description: "Phase 4a - Prompt Library (Module 7). A versioned library of LLM prompt templates, extending Phase 0's 18 already-verified templates (see insurance-ai-platform-phase0 repo and readme-runbook-phase1.md's Phase 0 summary for what was validated: llama3.1:8b, no hallucinations observed; phi3:mini disqualified for hallucinating claim IDs/policy numbers). This sub-phase covers the template structure and data-binding contract only - NO live LLM calls yet, that's 4b's job. Each template must explicitly declare which structured fields it draws from (e.g. a risk-assessment narrative template declares it may reference Customer, RiskAssessment, and RiskFactor fields, nothing else) - this whitelist IS the grounding contract that 4b's post-generation validator will check generated text against field-by-field. Reuse RULE_SET_VERSION-style versioning from apps/risk/rules.py's pattern for template versions. RBAC and audit logging reuse existing mechanisms - this module gets its own audit_routes.py entry, proving the registry as a fifth consumer. Tests first per constitution Principle V. This is the first of two planned specs (4a - templates and data-binding contract, then 4b - the actual LLM service integration and post-generation validator)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A Prompt Template Declares Exactly What Data It May Use (Priority: P1)

Someone responsible for the platform's AI outputs opens a prompt template —
say, the risk-assessment narrative — and can read, as an explicit part of the
template itself, the complete list of structured business fields that template
is permitted to draw from: certain Customer fields, certain RiskAssessment
fields, certain RiskFactor fields, and nothing else. There is no way to read
the template and be uncertain about what data it is allowed to touch, and no
field can be silently referenced by the template's text without appearing in
that declaration.

**Why this priority**: This declaration *is* the feature. Everything else in
Phase 4a exists to hold it. The declared field list is the grounding contract
that Phase 4b's post-generation validator will check generated text against,
field by field — a template whose declaration is incomplete, inaccurate, or
merely advisory would make that validator check the wrong thing, and the
platform's central defense against hallucinated claim IDs and policy numbers
would silently be checking nothing. Without this story there is no Phase 4a.

**Independent Test**: Take any template in the library, read its declared
field list, and confirm by inspection of the template body that every field
the body references appears in the declaration and every field in the
declaration is a real, currently-existing field on an *eligible* business
record type. Then attempt to add a template that references an undeclared
field, and separately one that declares a genuinely-existing field on an
ineligible record type (a platform user's credentials, an audit entry), and
confirm the platform rejects both.

**Acceptance Scenarios**:

1. **Given** a template in the library, **When** its declared field list is
   read, **Then** it names each permitted field as a specific field on a
   specific business record type (e.g. "the customer's age", "the
   assessment's tier"), not as a whole record type or a vague category.
2. **Given** a template whose body references a field that is not in its
   declared field list, **When** the library is validated, **Then** that
   template is rejected with an error naming the undeclared field — the
   library does not load in a partially-valid state.
3. **Given** a template whose declared field list names a field that does not
   exist on the business record type it claims, **When** the library is
   validated, **Then** that template is rejected with an error naming the
   nonexistent field.
4. **Given** a template declaring a field that genuinely exists but belongs to
   a record type outside the approved set — a platform user's role or
   credentials, or an audit trail entry — **When** the library is validated,
   **Then** that template is rejected because the record type itself is not
   eligible, not merely because the field is missing.
5. **Given** a template that declares a field it never actually references in
   its body, **When** the library is validated, **Then** that over-broad
   declaration is rejected — the declaration is an exact contract, not an
   upper bound, so a stale entry cannot silently widen what Phase 4b's
   validator will accept.

---

### User Story 2 - Every Template Carries a Version That Cannot Drift (Priority: P1)

An operator looks at any prompt template and can tell exactly which version of
that template's text and field declaration is in force. When a template's text
or its declared field list changes, the version changes with it. A version
recorded alongside a future generated output unambiguously identifies the
exact template content that produced it, so an output produced months ago
remains interpretable even after the template has since been revised.

**Why this priority**: The platform's audit obligation (constitution
Principle II) requires AI-generated outputs to be logged with the prompt
template used to produce them. A template reference with no version is not an
audit record — it points at whatever the template happens to say today. This
must be structurally guaranteed from the moment templates exist, not retrofitted
in 4b after untraceable outputs have already been generated.

**Independent Test**: Read a template's version, change the template's body
text without changing the version, and confirm the platform detects and
rejects the mismatch. Repeat with a change to the declared field list.

**Acceptance Scenarios**:

1. **Given** any template in the library, **When** it is inspected, **Then**
   it carries a version identifier following the same convention the risk
   module's rule-set version already uses.
2. **Given** a template whose body text or declared field list has been
   changed, **When** the library is validated without the corresponding
   version having been changed, **Then** the change is detected and rejected
   — a version cannot silently come to mean two different template contents.
3. **Given** two templates in the library, **When** their versions are
   compared, **Then** each template is versioned independently — revising one
   template does not change the version of any other.

---

### User Story 3 - A Permitted Role Browses the Library, an Unpermitted One Cannot (Priority: P1)

A user in a role permitted to work with prompt templates lists the library
through the platform's API, sees each template's identity, version, purpose,
and declared field list, and can retrieve a single template's full detail. A
user in a role not permitted to do so is refused, and that refusal is
recorded in the platform's audit trail the same way refusals in the customer,
policy, claims, and risk modules already are.

**Why this priority**: Prompt templates are administrative configuration that
governs what the platform will later say about real customers (BRD Module 12
lists Prompt Templates alongside Users, Roles, and Permissions). Server-side
role enforcement is non-negotiable per constitution Principle III, and the
audited-route registry entry this story adds is what proves that registry
generalizes to a fifth consumer rather than having been fitted to four
specific modules.

**Independent Test**: Call the library's list and detail routes as a permitted
role and confirm success; call them as each unpermitted role and confirm
refusal; then query the audit trail and confirm both the successful views and
the refusals are recorded with this module's own action names and target type.

**Acceptance Scenarios**:

1. **Given** a user in a permitted role, **When** they list the prompt
   library, **Then** they receive every template's identity, version,
   purpose, and declared field list.
2. **Given** a user in a role not permitted to access prompt templates,
   **When** they attempt to list or retrieve a template, **Then** they are
   refused server-side, and the refusal is recorded in the audit trail as a
   refusal rather than as an ordinary not-found.
3. **Given** any successful or refused access to the prompt library, **When**
   the audit trail is queried, **Then** the entry carries this module's own
   action names and target type — distinguishable from customer, policy,
   claim, and risk entries.
4. **Given** the audited-route registry, **When** its registered entries are
   inspected, **Then** the prompt library appears as its own entry with its
   own role sets, added without modifying the behavior of the four existing
   entries.

---

### User Story 4 - The Library Covers Phase 0's Verified Prompt Set (Priority: P2)

The library contains the full set of prompt types Phase 0 exercised against a
local model — risk summary, fraud summary, FNOL, emails, CRM notes, renewal,
cross-sell, executive summary, policy recommendation, dashboard summary, and
the rest of Phase 0's 18 — each now carrying the structure, versioning, and
field declaration the earlier stories require. A template whose Phase 0
counterpart depended on data this platform does not yet have is either
declared against fields that do exist or explicitly deferred, never carried
over with a declaration the platform cannot honor.

**Why this priority**: Coverage is what makes the library useful to Phase 4b
and Module 9, but it is worth less than getting the contract right — a large
library of loosely-declared templates would be actively worse than a small
correct one. Stories 1-3 are the load-bearing work; this story is the payload
they carry.

**Independent Test**: Enumerate the library and confirm each Phase 0 prompt
type is present or explicitly recorded as deferred with a reason, and that
every present template independently satisfies Stories 1 and 2.

**Acceptance Scenarios**:

1. **Given** the library as shipped, **When** it is enumerated, **Then** each
   of Phase 0's prompt types is either present as a template or recorded as
   deliberately deferred with a stated reason.
2. **Given** a Phase 0 prompt type whose data needs are not fully met by the
   business records that exist today (e.g. fraud-specific or behavior-specific
   data from modules not yet built), **When** it is carried into the library,
   **Then** it is declared only against fields that actually exist, or it is
   deferred — it is never declared against a field the platform cannot supply.
3. **Given** the library as shipped, **When** each template's declared model
   preference is inspected, **Then** it reflects Phase 0's finding — the model
   that produced no observed hallucinations is the recorded preference, and the
   model disqualified for fabricating claim IDs and policy numbers is recorded
   as disqualified with that reason.

---

### Edge Cases

- What happens when a template declares a field that exists today but is later
  renamed or removed by a future migration? The library's validation must fail
  loudly at that point rather than silently permitting a declaration that no
  longer maps to anything — a dangling declaration would make Phase 4b's
  validator check a field that does not exist.
- What happens when a template needs to reference a field on a record the
  platform does not yet have (fraud scores, behavior classifications, CRM
  records)? It cannot be declared; the template is deferred rather than
  admitted with an unhonorable declaration.
- What happens when a template declares a field that genuinely exists, but on
  a record type that is not business data at all — a platform user's password
  hash, role, or permission flags, or an audit trail entry? Field-existence
  checking alone would pass it, since the field really does exist. The eligible
  record type whitelist is what rejects it. Audit entries are the sharpest
  case: their before/after state snapshots would otherwise re-expose any field
  of any other record type — including ineligible ones — through a single
  approved declaration.
- What happens when a future module (Fraud, Behavior, CRM) adds record types
  its own templates need to draw from? The whitelist must be amended
  deliberately as part of that module's spec. A new record type does not become
  declarable merely by existing.
- What happens when a template's declaration would permit a field that is
  personally identifying or a protected characteristic (e.g. a customer's
  gender, which the risk rule set deliberately excludes from scoring)? Whether
  such fields may appear in a declaration MUST be a deliberate, recorded
  decision per template, not an accident of whichever fields the template
  author happened to reference.
- What happens when two templates in the library are given the same identity?
  The library must reject the collision rather than let one silently shadow the
  other, since a later audit record naming that identity would be ambiguous.
- What happens when the library is empty or a requested template does not
  exist? A request for a nonexistent template from a permitted role is an
  ordinary not-found; the same request from an unpermitted role is a refusal —
  the same distinction the existing audited-route registry already draws.
- What happens if a template's body contains a placeholder that binds to no
  declared field at all (a typo, or a leftover from Phase 0's free-form
  prototyping)? It is rejected — an unbound placeholder would either render as
  literal text into a prompt or silently render as empty, and both are wrong.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST provide a library of named prompt templates,
  each identified by a stable identifier that is unique across the library.
- **FR-002**: Each template MUST carry a human-readable purpose describing
  what output it is intended to produce and for which business audience.
- **FR-003**: Each template MUST carry a body: the prompt text, with explicit
  placeholders marking every position where structured business data is to be
  bound in.
- **FR-004**: Each template MUST carry an explicit declaration of every
  structured business field it may draw from. Each declared entry MUST name a
  specific field on a specific business record type (e.g. the customer's age,
  the assessment's tier), never a whole record type and never a category.
- **FR-005**: The declaration in FR-004 MUST be exact in both directions: every
  field referenced by a template's body MUST appear in its declaration, and
  every field in its declaration MUST be referenced by its body. Neither an
  undeclared reference nor an unused declared field is permitted.
- **FR-006**: Every field named in a template's declaration MUST correspond to
  a field that actually exists on the business record type it names. A
  declaration naming a nonexistent field MUST be rejected.
- **FR-007**: Every placeholder in a template's body MUST bind to exactly one
  declared field. A placeholder that binds to nothing MUST be rejected.
- **FR-008**: The platform MUST validate FR-005, FR-006, and FR-007 for the
  entire library as a unit, and MUST fail loudly and completely when any
  template violates them — the library MUST NOT load in a partially-valid
  state where some templates passed and others were skipped.
- **FR-009**: Each template MUST carry a version identifier that follows the
  same convention the platform's existing risk rule-set version already uses,
  and that is versioned independently per template.
- **FR-010**: A template's version MUST change whenever its body or its
  declared field list changes. The platform MUST detect and reject a changed
  template whose version was not changed with it, so that one version can
  never denote two different template contents.
- **FR-011**: The platform MUST expose the library for reading through its
  API: a way to list all templates with their identity, purpose, version, and
  declared field list, and a way to retrieve one template's full detail
  including its body.
- **FR-012**: Access to the prompt library MUST be enforced server-side by
  role, using the platform's existing role-based access mechanism. No prompt
  library route may rely on client-side or presentation-layer restriction.
- **FR-013**: The prompt library MUST be registered as its own entry in the
  platform's existing audited-route registry, with its own route prefix, its
  own target type, its own action names, and its own view and write role sets
  — becoming the registry's fifth consumer alongside customers, policies,
  claims, and risk.
- **FR-014**: Registering the prompt library per FR-013 MUST NOT alter the
  behavior of any of the four existing registry entries.
- **FR-015**: Every *refused* access to the prompt library, and every write to
  it if a write route exists, MUST be recorded in the platform's existing
  append-only audit trail using this module's own action names and target type,
  and a refusal MUST be distinguishable in that trail from an ordinary
  not-found, following the same per-module role-set convention the registry
  already implements. Successful reads are NOT recorded — this matches the
  platform's established behavior in every existing module (no module audits
  successful reads), which FR-013/FR-014 require this module to share as the
  registry's fifth consumer. *(Narrowed during planning from "every access —
  successful or refused"; see `research.md` §7 and plan.md's Complexity
  Tracking. Auditing successful reads would be a platform-wide convention
  change belonging in its own spec.)*
- **FR-016**: The library MUST cover the prompt types Phase 0 validated —
  **seven** templates, verified against the Phase 0 artifacts during planning.
  Any Phase 0 prompt type not carried into the library MUST be recorded as
  deliberately deferred, with a stated reason. A template MUST NOT be added to
  the library merely to reach a target count; every template MUST trace to a
  Phase 0 prompt type or be justified on its own terms.
- **FR-017**: A template MUST NOT be admitted to the library with a
  declaration naming a field the platform does not currently have. A template
  whose intended data needs cannot be met by existing business records MUST be
  deferred instead (per FR-016), never admitted with an unhonorable
  declaration.
- **FR-018**: Each template MUST record the model preference established by
  Phase 0's evaluation, including which evaluated model was disqualified and
  the reason for that disqualification, so the finding survives as data in the
  platform rather than only as prose in a runbook.
- **FR-019**: The platform MUST NOT make any call to a language model as part
  of this feature. The library is inert configuration in Phase 4a: templates
  are defined, validated, versioned, and served, but never executed.
- **FR-020**: The declared field list MUST be readable programmatically, in a
  form a later post-generation validator can consume field-by-field without
  re-parsing the template body — it is the machine-checkable grounding
  contract, not documentation about one.
- **FR-021**: For each template, whether personally-identifying fields or
  protected characteristics may appear in its declaration MUST be a recorded,
  deliberate per-template decision, not an implicit consequence of what the
  body happens to reference.
- **FR-022**: The library's templates and their validation MUST have tests
  written before or alongside the implementation, per the constitution's
  test-first principle for business-rule code, covering the deterministic
  surface: declaration/body agreement, field existence, version-content
  agreement, identifier uniqueness, record-type eligibility, role enforcement,
  and audit recording.
- **FR-023**: The set of business record types eligible to be named in any
  template's declaration MUST be an explicit, closed whitelist, enforced as
  a hard check rather than stated only in prose. A declaration naming a record
  type outside the whitelist MUST be rejected, even when the field it names
  genuinely exists on that type. Field existence (FR-006) is necessary but not
  sufficient: a template may only draw from record types the platform has
  deliberately approved as groundable business data.
- **FR-024**: The whitelist in FR-023 MUST be pinned by an exact-equality
  check in both directions — no record type outside it may be declared
  against, and no record type inside it may be silently dropped — following
  the same enforcement pattern the risk module already uses to pin its
  approved factor set. Changing the whitelist MUST require amending FR-023 and
  its enforcing assertion deliberately, not merely adding a declaration that
  happens to validate.
- **FR-025**: Identity, authentication, authorization, and audit record types
  MUST NOT appear in the FR-023 whitelist. A template MUST NOT be able to
  declare against a platform user's credentials, role, or permission flags, nor
  against audit trail entries — including the before/after state snapshots
  audit entries carry, which would otherwise re-expose any field of any other
  record type through an approved one.

### Key Entities

- **Prompt Template**: One named, versioned prompt in the library. Carries its
  stable identifier, its human-readable purpose, its body text with
  placeholders, its declared field list, its version, and its recorded model
  preference. It is configuration that governs future AI output, not a record
  of any customer, policy, or claim.
- **Declared Field Binding**: One entry in a template's declaration — a
  specific field on a specific business record type that the template is
  permitted to draw from, paired with the placeholder in the body that binds
  it. The complete set of these for a template is the grounding contract that
  a later post-generation validator will check generated text against.
- **Template Version**: The identifier denoting an exact template body plus an
  exact declared field list, following the platform's existing rule-set
  versioning convention. Independent per template.
- **Audited Route Entry** *(existing mechanism, new entry)*: The prompt
  library's own registration in the platform's audited-route registry, giving
  the module its route prefix, target type, action names, and per-module view
  and write role sets. Adding it exercises the registry as a fifth consumer.
- **Eligible Record Type Whitelist**: The closed, explicitly-approved set of
  business record types a declaration may name — Customer, Policy, Claim,
  RiskAssessment, RiskFactor and nothing else. It is the outer boundary of the
  grounding contract: FR-004-008 constrain *which fields* of a record type a
  template may use, and this whitelist constrains *which record types are
  eligible at all*. Pinned by exact equality in both directions, so it cannot
  quietly grow or shrink.
- **Customer, Policy, Claim, RiskAssessment, RiskFactor** *(existing,
  unchanged)*: The business record types whose fields a template's declaration
  may name — the whitelist's exact membership. This feature reads their field
  definitions to validate declarations; it does not add to, modify, or read the
  data in any of them.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of templates in the library carry a declared field list in
  which every entry names a field that exists on the business record type it
  claims, and every field the template's body references appears — verified
  automatically, with zero templates exempt.
- **SC-002**: A template introduced with an undeclared field reference, an
  unused declared field, a nonexistent field, a field on an ineligible record
  type, an unbound placeholder, or a duplicate identifier is rejected 100% of
  the time, and the whole library fails to load rather than loading partially.
- **SC-002a**: The set of record types any template may declare against is
  exactly the approved five — verified by an exact-equality check that fails if
  a sixth is added or one of the five is dropped. Zero templates in the library
  declare against a platform user, an audit entry, or any other ineligible
  record type, and a template attempting to do so cannot load even though the
  field it names genuinely exists.
- **SC-003**: 100% of templates carry an independently-assigned version, and a
  change to any template's body or declaration without a matching version
  change is detected 100% of the time.
- **SC-004**: Every role permitted to read the prompt library can list and
  retrieve templates; every role not permitted is refused server-side 100% of
  the time, with zero routes relying on presentation-layer restriction.
- **SC-005**: 100% of *refused* prompt library accesses appear in the
  platform's audit trail with this module's own action names and target type,
  recorded as a refusal rather than as an ordinary not-found; and successful
  reads add zero audit rows, matching every other module (per FR-015 as
  narrowed).
- **SC-006**: The four pre-existing audited-route consumers behave identically
  before and after the prompt library's entry is added — every existing test
  covering their routing, role sets, and audit outcomes still passes unchanged.
- **SC-007**: Every prompt type Phase 0 validated is accounted for in the
  library — present as a template, or recorded as deferred with a stated
  reason — with none silently dropped.
- **SC-008**: Zero language-model calls occur anywhere in this feature's code
  paths or its test suite.
- **SC-009**: A reader given only a template's declared field list can state
  exactly which business fields any output from that template may reference,
  without reading the template's body.

## Assumptions

- **Phase 0's findings were reconciled during planning. The count was wrong;
  the model findings were right.** *(This bullet originally recorded the Phase 0
  claims as taken-as-given and unverifiable from this repository. They are now
  verified — the Phase 0 repo exists at `~/insurance-ai-platform-phase0`,
  outside this project's directory, which is why the specification pass could
  not see it.)* Verified: the library is **7 templates, not 18**
  (`app.py:43-101` defines seven; `readme-setup-conclusions.md:192` states "All
  7 prompt templates tested"). Both model findings are confirmed verbatim —
  `llama3.1:8b` rated usable on 8/8 runs, `phi3:mini` disqualified for
  hallucinating claim IDs and policy numbers
  (`readme-setup-conclusions.md:121-124`). FR-016 has been corrected to seven;
  FR-018 needed no change. Full reconciliation in `research.md` §1.
- **Five of the seven Phase 0 templates reference a field the platform does not
  have.** `Client_Feedback` (in 5 of 7) and `Last_Interaction` are Phase 0 CSV
  columns with no corresponding model field anywhere. Under FR-006 and FR-017
  they cannot be declared, so those five are carried over *rewritten* to drop
  the reference, each recording that divergence in its own metadata rather than
  implying an untouched port. Deferring them would leave a two-template library;
  adding a `feedback` column to `Customer` to accommodate a prompt would invert
  the dependency the grounding contract exists to establish. See `research.md` §2.
- Per constitution Principle VI, Phase 0's spike code is not a refactoring
  starting point. Its prompt *text* and its model findings inform this
  library's content, but the templates are authored fresh under this spec.
- The library is defined in version-controlled source rather than as
  operator-editable database rows. BRD Module 12 lists Prompt Templates under
  Administration, implying eventual runtime editing; that is a later concern.
  Phase 4a's contract is only meaningful if it is validated at load time and
  reviewable in a diff, which a code-resident library gives and a
  free-text admin field does not.
- The declared field list names fields on the platform's existing business
  record types, and FR-023/FR-024 fix that set at exactly Customer, Policy,
  Claim, RiskAssessment and RiskFactor. Record types belonging to modules not
  yet built — Fraud, Behavior, CRM — cannot be declared against, so Phase 0
  prompt types depending on them are expected to be deferred under
  FR-016/FR-017 rather than admitted. When those modules arrive, adding their
  record types to the whitelist is a deliberate amendment in their own spec,
  not something this spec pre-authorizes.
- Read access is **universal — all nine roles** — and write access is **System
  Administrator alone**. *(Settled during planning; the spec originally assumed
  "broad but not universal" reads.)* A template carries field *names*, never
  field *values*, so it holds no customer data and the restrictions protecting
  the other four modules have nothing to protect here; Executive Leadership,
  excluded from all four existing view sets, can read prompt templates. This is
  a genuinely fifth shape in both halves — the first universal view set and the
  first single-role write set on the platform. See `research.md` §4.
- "Version" follows the existing rule-set convention (a semantic-version string
  constant in code, changed deliberately when content changes), including its
  established discipline that the version is stamped onto any downstream record
  produced under it.
- Rendering is **out of scope for 4a; the resolver is in scope**. *(Settled
  during planning.)* 4a ships declaration → value resolution, which is what 4b's
  post-generation validator needs to check generated text field-by-field. It
  does not ship value → finished-prompt-string rendering, whose only consumer is
  4b's LLM service and whose design depends on prompt-assembly needs (system
  prompts, few-shot examples, output-format instructions) that do not exist yet.
  Either way, no language model is called (FR-019). See `research.md` §6.
- Phase 4b will consume this library's declared field lists to validate
  generated text field-by-field. Phase 4a delivers the contract and its
  enforcement; the validator, the model integration, and any persistence of
  generated output are explicitly out of scope.
- Placeholder syntax is **`{RecordType.field_name}`** — e.g. `{Customer.name}`.
  *(Settled during planning; the spec originally left the syntax open.)* A
  qualified placeholder makes the body self-describing, so FR-005's
  both-directions check is a set comparison with no inference step. A bare
  `{name}` would need a rule for which record type owns a field, ambiguous the
  moment two eligible types share a name — and three already do (`archived_at`
  on Customer, Policy and Claim). A full template language was rejected because
  conditionals and loops would make FR-007 undecidable by static inspection.
  See `research.md` §5.
- Constitution Principle IV (explainable AI outputs) is satisfied structurally
  by this phase rather than behaviorally: the declared field list is what makes
  a later generated output traceable to the exact structured data it was
  permitted to draw from. The explanation-and-human-review obligations attach
  to the outputs Phase 4b produces, not to the inert templates delivered here.
