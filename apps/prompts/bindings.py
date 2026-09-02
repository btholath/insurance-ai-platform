"""
The binding primitives and the eligible-record-type whitelist (T011-T014).

NO DJANGO IMPORT. Not the ORM, not settings, not TextChoices. This mirrors
`apps/risk/rules.py`'s first structural property and exists for the same
reason: the primitives are pure values over plain strings, which is what lets
`test_bindings.py` exercise every extraction and eligibility case without a
database. `validation.py` owns the translation from these strings to real
model fields -- keeping that boundary means a binding bug is reproducible from
a REPL with no fixtures.

Two things are load-bearing here.

1. THE WHITELIST IS THE OUTER BOUNDARY OF THE GROUNDING CONTRACT.
   FR-004-008 constrain WHICH FIELDS of a record type a template may use.
   This frozenset constrains WHICH RECORD TYPES are eligible at all. Field
   existence is necessary but NOT sufficient -- see the comment on
   ELIGIBLE_RECORD_TYPES below for the attack this closes.

2. PLACEHOLDERS ARE QUALIFIED, ALWAYS. `{Customer.name}`, never `{name}`.
   A qualified placeholder makes a template body self-describing, so
   validation is a set comparison between what the regex extracts and what the
   template declares, with no inference step that could disagree. An
   unqualified token would need a rule for which record type owns a bare field
   name, and that is ambiguous the moment two eligible types share one --
   `archived_at` is on Customer, Policy AND Claim today.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# FR-023/FR-024. The closed set of record types a template may declare
# against. Pinned by exact equality in BOTH directions in
# test_bindings.py::test_eligible_record_types_is_exactly_the_approved_five --
# a subset check would admit a sixth type, a superset check would let one be
# silently dropped.
#
# Strings, not model classes, so this module stays Django-free.
# `validation.py` resolves them through the app registry.
#
# WHAT IS DELIBERATELY ABSENT, AND WHY (FR-025):
#
#   User      -- `password` (a credential hash), `is_superuser` and `role` are
#                all REAL fields on it (AbstractBaseUser + PermissionsMixin).
#                A field-existence check alone would admit every one of them.
#   AuditLog  -- `before` and `after` are real JSONFields holding prior-state
#                snapshots of OTHER records. This is the sharpest case: one
#                approved declaration against them would re-expose arbitrary
#                fields of arbitrary record types -- including the ineligible
#                ones -- through a single entry that passes every other check.
#                A full bypass of the grounding contract.
#
# Adding a record type here is a deliberate amendment to FR-023, not something
# that happens because a new template wanted it.
ELIGIBLE_RECORD_TYPES = frozenset(
    {
        "Customer",
        "Policy",
        "Claim",
        "RiskAssessment",
        "RiskFactor",
    }
)


@dataclass(frozen=True)
class FieldBinding:
    """
    One declared field: a specific field on a specific record type, paired
    with the placeholder in the body that binds it.

    Frozen so a template's declaration cannot be mutated after definition, and
    hashable so the set comparisons in validation.py are cheap and exact.
    """

    record_type: str
    field_name: str
    placeholder: str


# Matches `{RecordType.field_name}`. The record type is capitalised (matching
# Django model class names) and the field name is a lowercase identifier
# (matching Django field naming), so a bare `{name}` or a `{lowercase.thing}`
# simply does not match -- it is not silently reinterpreted.
#
# The surrounding (?<!\{) / (?!\}) guards implement the `{{` / `}}` escape:
# a doubled brace is a literal, per str.format convention.
PLACEHOLDER_RE = re.compile(
    r"(?<!\{)\{([A-Z][A-Za-z0-9]*)\.([a-z_][a-z0-9_]*)\}(?!\})"
)


def extract_placeholders(body):
    """
    Every `(record_type, field_name)` pair the body references, as a set.

    A set, not a list: the same placeholder used twice is one binding, and
    FR-005's both-directions check is a set comparison.

    Returns nothing for an unqualified `{name}` -- see the module docstring.
    That token then has no matching binding, and validation rejects it as an
    unbound placeholder (FR-007), which is the loud failure we want rather
    than a silent guess about which record owns `name`.
    """
    return set(PLACEHOLDER_RE.findall(body))


class UnresolvedBinding(Exception):
    """Raised when no record was supplied for a binding's record type."""


def resolve(template, **records):
    """
    Declaration -> value, for one template against supplied records (FR-020).

    RESOLVER ONLY. This deliberately does NOT substitute values into the body
    to produce a finished prompt string. Rendering has exactly one consumer --
    Phase 4b's LLM service -- and its shape depends on prompt-assembly
    decisions that do not exist yet (system prompts, few-shot examples,
    output-format instructions). Building it here would mean designing against
    a service nobody has written.

    The resolver is the genuinely reusable half: Phase 4b's post-generation
    validator needs VALUES BY DECLARED FIELD to check generated text
    field-by-field, which is exactly this function's output.

    Records are passed by lowercased record type -- `resolve(t,
    customer=c, policy=p, ...)`. Returns `{FieldBinding: value}`.

    The returned keys are exactly the template's declared bindings, never
    more: nothing outside the declaration can appear in the output, which is
    the grounding contract holding at the value layer rather than only at the
    schema layer.
    """
    resolved = {}
    for binding in template.bindings:
        key = binding.record_type.lower()
        if key not in records or records[key] is None:
            raise UnresolvedBinding(
                f"no {binding.record_type} supplied for "
                f"{binding.record_type}.{binding.field_name}"
            )
        resolved[binding] = getattr(records[key], binding.field_name)
    return resolved
