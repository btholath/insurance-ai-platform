<!--
Sync Impact Report
==================
Version change: 1.0.0 → 1.0.1 (patch clarification)

Modified principles: N/A (no principle text or requirements changed)

Added sections: N/A

Removed sections: N/A

Other changes:
- Corrected all Spec Kit slash-command references from dot notation
  (`/speckit.specify`, `/speckit.plan`, `/speckit.tasks`, `/speckit.implement`,
  `/speckit.constitution`) to hyphen notation (`/speckit-specify`,
  `/speckit-plan`, `/speckit-tasks`, `/speckit-implement`,
  `/speckit-constitution`), matching the actually-installed CLI syntax.
- Removed the reference to `/code-review` in Development Workflow & Quality
  Gates (not a real installed skill — only `speckit-*` skills exist in
  `.claude/skills/`); replaced with a generic "human code review"
  requirement, naming no specific tool.

Follow-up TODOs:
- TODO(RATIFICATION_DATE): Original adoption date not supplied by user; set to
  2026-07-28 (the date of initial ratification) since this is the first
  concrete version of the constitution. Confirm with project owner if a
  different historical date should apply.
-->

# Insurance AI Platform Constitution

## Core Principles

### I. Local-First, No Cloud Dependencies
The platform MUST run entirely on local infrastructure — WSL Ubuntu, PostgreSQL,
Redis, and Ollama-hosted models (Llama 3, Mistral, DeepSeek, and other
Ollama-compatible models) — with no required calls to external cloud APIs or
managed SaaS services. Any integration with a hosted/cloud LLM or service
(e.g., a future Claude API or OpenAI-compatible endpoint) MUST be optional,
config-gated, and never a dependency for core functionality to run offline.
Rationale: this is a portfolio/reference platform demonstrating local AI
architecture; a hard dependency on external services would break the
"runs entirely on my machine" value proposition and introduce data-egress
risk for insurance PII.

### II. Auditability by Default
Every module that creates, modifies, or acts on Customer, Policy, Claim, Risk,
Fraud, or CRM data MUST write to the audit log (who, what, when, before/after
state where applicable). AI-generated outputs (summaries, scores, prompts
executed) MUST be logged with the prompt template, model, and inputs used to
produce them. Audit log records MUST be treated as append-only — no module
may update or delete existing audit entries. Rationale: the BRD scopes Audit
Logs as a first-class module (Module 12) and a non-functional security
requirement; retroactive logging cannot reconstruct investigative or
compliance history for fraud/claims decisions.

### III. Role-Based Access Control (NON-NEGOTIABLE)
Every module MUST enforce role-based access control at the view/API layer,
not just hide UI elements. Roles defined by the BRD (Fraud Analyst, Claims
Adjuster, Customer Service, Underwriter, Compliance Officer, Risk Manager,
Product Manager, Executive Leadership, System Administrator) MUST map to
explicit permissions checked server-side. No endpoint may rely on
client-side or template-only access restriction. Rationale: this is an
insurance platform handling PII and fraud investigation data; unauthorized
cross-role access (e.g., Customer Service viewing fraud investigation
queues) is a compliance failure, not a UX nicety.

### IV. Explainable AI Outputs
Any AI/LLM-generated output that influences a business decision (risk score,
fraud score, fraud indicator, renewal probability, behavior classification)
MUST be accompanied by a human-readable explanation of the contributing
factors, and MUST be presented as a recommendation for human review rather
than an automatic action, unless a future spec explicitly defines an
autonomous-action workflow with its own approval gate. Raw LLM output MUST
NOT be persisted as the sole record of a decision — the structured
score/classification plus its explanation is the record of truth, with the
raw generation retained only as supporting audit detail. Rationale: the BRD
requires "Provide explainable AI decisions" and "Support human review" as
core business goals; insurance risk/fraud decisions carry regulatory and
customer-trust consequences that opaque model output cannot satisfy alone.

### V. Test-First for Business Rules (NON-NEGOTIABLE)
All business-rule code — risk scoring, fraud detection, renewal probability,
behavior/retention scoring, and any other deterministic or rule-based
scoring logic — MUST have pytest tests written before or alongside
implementation, using Factory Boy for test data construction, and MUST
maintain measured coverage for that code (no merging business-rule logic
with untested branches). CRUD-only code (simple model/view boilerplate) is
exempt from mandatory TDD ordering but still requires tests before merge.
Prompt templates and LLM-integration code MUST have tests around their
deterministic surface (input construction, output parsing/validation,
fallback behavior) even though raw model output is non-deterministic and
not itself asserted against. Rationale: risk and fraud scoring are the
platform's core value and its highest-liability surface — regressions here
are silent and costly, and coverage tooling is the only reliable backstop
since business stakeholders can't manually re-verify every scoring path.

### VI. Disposable Prototyping Stays Disposable
The Phase 0 Streamlit spike (CSV + Ollama, no auth/roles/persistence) is
explicitly exempt from spec-driven development and from Principles I–V. It
MUST NOT be scaffolded as a formal module, MUST NOT be run through
`/speckit-specify` or subsequent Spec Kit commands, and MUST NOT be treated
as a dependency of any production module. Findings from the spike (prompt
quality, model choice, response latency) MAY inform the real spec for
Module 7 (Prompt Library) and Module 8 (LLM Services), but the spike's code
is not a starting point to refactor into production — production
implementations start fresh under full spec-driven workflow. Rationale: the
BRD explicitly designates Phase 0 as throwaway, vibe-coded prototyping; over
adherence to constitution/testing rules on disposable code wastes the speed
advantage it exists to provide, while accidentally promoting spike code to
production would import untested, unaudited, non-RBAC'd logic into a
platform that requires all three.

## Technology Stack Constraints

The following stack is binding for all spec-driven (non-Phase-0) work unless
a future amendment changes it:

- **Language/Runtime**: Python 3.13
- **Web Framework**: Django 5.x with Django REST Framework for APIs
- **Database**: PostgreSQL 16+ with the `pgvector` extension for embeddings/
  vector search (FAISS may be used only if pgvector proves insufficient for
  a specific spec, with rationale recorded in that spec's plan)
- **Cache/Queue Broker**: Redis
- **Background Jobs**: Celery
- **LLM Runtime**: Ollama, serving Llama 3, Mistral, DeepSeek, and other
  locally hosted models; OpenAI-compatible or cloud APIs (e.g., Claude API)
  are future-optional per Principle I, never required
- **Testing**: pytest + Factory Boy, with coverage measurement required for
  business-rule code per Principle V
- **Target Environment**: WSL Ubuntu on Windows 11, Docker/Docker Compose
  for service orchestration; no production cloud deployment is in scope

Deviating from this stack (e.g., swapping Django for another framework, or
introducing a mandatory cloud dependency) requires a constitution amendment,
not a one-off implementation decision.

## Development Workflow & Quality Gates

- Every formal module (Customer, Policy, Claims, Risk, Fraud, Behavior,
  Prompt Library, LLM Services, CRM, Dashboards, Reporting, Administration)
  MUST go through the Spec Kit lifecycle (`/speckit-specify` →
  `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`) rather than
  being hand-built ad hoc.
- Specs and plans MUST call out, for each module, how Principles II
  (audit logging), III (RBAC), and IV (explainability) are satisfied — a
  plan that is silent on these is incomplete, not merely light.
- Human code review MUST verify that new business-rule code has accompanying
  tests and that new endpoints enforce role checks before merge is
  considered complete.
- The Phase 0 spike is the sole exception to the above, per Principle VI.

## Governance

This constitution supersedes ad hoc conventions and prior informal practice
for all spec-driven work in this repository. Where a spec, plan, or task
conflicts with this constitution, the constitution wins unless the
constitution itself is amended first.

**Amendment procedure**: Amendments are proposed by editing this file via
`/speckit-constitution`, which regenerates the Sync Impact Report, bumps the
version per the policy below, and updates `Last Amended`. Amendments should
briefly state the motivating reason (new requirement, discovered gap,
stack change) either in the commit message or the Sync Impact Report.

**Versioning policy** (semantic versioning applied to governance):
- **MAJOR**: Backward-incompatible removal or redefinition of a principle
  (e.g., dropping the local-first requirement, weakening RBAC to optional).
- **MINOR**: A new principle or section is added, or existing guidance is
  materially expanded (e.g., adding a new mandatory module-level gate).
- **PATCH**: Clarifications, wording fixes, typo corrections, or
  non-semantic refinements that don't change what is required.

**Compliance review**: Every module's spec/plan MUST be checked against
Principles I–VI before `/speckit-tasks` is run for that module. Any
justified exception (e.g., a module that genuinely cannot satisfy a
principle) MUST be documented in that module's plan under a "Constitution
Exceptions" note with rationale, rather than silently ignored.

**Version**: 1.0.1 | **Ratified**: 2026-07-28 | **Last Amended**: 2026-07-29
