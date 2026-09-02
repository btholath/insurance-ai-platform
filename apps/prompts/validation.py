"""
Whole-library validation: the grounding contract's enforcement point
(T023-T026, US1).

THIS MODULE OWNS THE ORM BOUNDARY. `bindings.py` and `library.py` import no
Django; this one does, because checking that a declared field exists means
asking a real model. Keeping the boundary here is what lets the library and
its primitives stay testable without a database.

Three properties are structural rather than policed by convention:

1. ELIGIBILITY IS CHECKED BEFORE EXISTENCE, AND THE ORDER MATTERS.
   `User.password` is a real field. So are `User.is_superuser` and
   `AuditLog.before`. If existence were checked first, those would resolve
   happily and the whitelist would never be consulted -- so a caller would
   see no error at all. Checking eligibility first means the error a caller
   gets for `User.password` names the RECORD TYPE as ineligible, which is the
   true reason. `test_declared_record_type_must_be_eligible` asserts on that
   message specifically, so this ordering cannot be quietly inverted.

2. THE DECLARATION IS EXACT IN BOTH DIRECTIONS (FR-005). Set EQUALITY between
   what the body references and what the template declares -- not containment
   either way. An undeclared reference means generated text could cite data no
   one approved; an unused declaration means the contract silently permits
   more than the template can actually produce, which widens what Phase 4b's
   validator will accept. Both are contract failures, so both raise.

3. VALIDATION IS ALL-OR-NOTHING (FR-008). `validate_library` raises on the
   first bad template and validates nothing partially. A library where some
   templates passed and others were skipped would have no way to tell a
   reader which ones carry an enforced contract.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.apps import apps as django_apps
from django.core.exceptions import FieldDoesNotExist

from .bindings import ELIGIBLE_RECORD_TYPES, extract_placeholders


class LibraryError(Exception):
    """
    Raised for any contract violation.

    Deliberately one exception type rather than a hierarchy: every violation
    here is fatal at app-ready in exactly the same way, and the message
    carries the distinguishing detail. Callers do not branch on the kind of
    failure -- they fail to start.
    """


@dataclass(frozen=True)
class TemplateShape:
    """
    The minimum a thing needs to be validated: an identifier, a body, and a
    tuple of FieldBindings.

    `library.PromptTemplate` satisfies this structurally without inheriting
    from it, which is what lets `test_validation.py` construct fixtures
    without importing the real library -- US1's validation is exercisable
    before US4 authors a single template.
    """

    identifier: str
    body: str
    bindings: tuple


# The five eligible record types live in these apps. An explicit map rather
# than a search across all installed apps: two apps could define models with
# the same class name, and a search would make which one wins an accident of
# app ordering.
_RECORD_TYPE_APPS = {
    "Customer": "customers",
    "Policy": "policies",
    "Claim": "claims",
    "RiskAssessment": "risk",
    "RiskFactor": "risk",
}


def _model_for(record_type):
    return django_apps.get_model(_RECORD_TYPE_APPS[record_type], record_type)


def check_binding(binding):
    """
    One declared field. Eligibility first (FR-023), then existence (FR-006).

    See the module docstring's property 1 for why that order is load-bearing.
    """
    if binding.record_type not in ELIGIBLE_RECORD_TYPES:
        raise LibraryError(
            f"record type {binding.record_type!r} is not eligible to be "
            f"declared against (FR-023). Eligible types are "
            f"{sorted(ELIGIBLE_RECORD_TYPES)}. Note this is not a question of "
            f"whether {binding.record_type}.{binding.field_name} exists -- "
            f"identity, authorization and audit records are permanently "
            f"ineligible (FR-025) precisely because their fields do exist."
        )

    model = _model_for(binding.record_type)
    try:
        model._meta.get_field(binding.field_name)
    except FieldDoesNotExist:
        raise LibraryError(
            f"no such field {binding.record_type}.{binding.field_name!r} "
            f"(FR-006). A declaration naming a field that does not exist "
            f"would give Phase 4b's validator nothing to resolve -- this also "
            f"catches a field renamed or removed by a later migration."
        ) from None


def check_template(template):
    """
    One template: every binding, then body/declaration set equality.

    A binding failure is re-raised with the template's identifier prepended.
    `check_binding` knows the offending field but not which template holds it,
    and an error naming only `Customer.nope` across a seven-template library
    tells a reader what is wrong without telling them where -- so the two
    halves are joined here, where both are in scope.
    """
    for binding in template.bindings:
        try:
            check_binding(binding)
        except LibraryError as exc:
            raise LibraryError(f"template {template.identifier!r}: {exc}") from None

    referenced = extract_placeholders(template.body)
    declared = {(b.record_type, b.field_name) for b in template.bindings}

    undeclared = referenced - declared
    if undeclared:
        names = sorted(f"{rt}.{fn}" for rt, fn in undeclared)
        raise LibraryError(
            f"template {template.identifier!r} references undeclared "
            f"field(s) {names} (FR-005). Every field a body references must "
            f"appear in its declaration -- the declaration is the contract "
            f"Phase 4b checks generated text against."
        )

    unused = declared - referenced
    if unused:
        names = sorted(f"{rt}.{fn}" for rt, fn in unused)
        raise LibraryError(
            f"template {template.identifier!r} declares field(s) {names} that "
            f"its body never references (FR-005). The declaration is an exact "
            f"contract, not an upper bound: a stale entry would silently widen "
            f"what Phase 4b's validator accepts."
        )


def validate_library(templates):
    """
    The whole library as a unit. Raises on the first violation and validates
    nothing partially (FR-008).

    Called from `PromptsConfig.ready()`, so a malformed library fails at
    startup -- the loudest failure available.
    """
    seen = set()
    for template in templates:
        if template.identifier in seen:
            raise LibraryError(
                f"duplicate template identifier {template.identifier!r} "
                f"(FR-001). Identifiers must be unique across the library, "
                f"or a later audit record naming one would be ambiguous about "
                f"which template produced the output."
            )
        seen.add(template.identifier)

    for template in templates:
        check_template(template)
