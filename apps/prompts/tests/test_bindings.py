"""
Binding primitives and the eligible-record-type whitelist (T005-T010).

Nothing here touches the database. `apps.prompts.bindings` imports no Django,
so these run as pure value tests -- the same property `apps/risk/rules.py`
maintains and for the same reason: a binding bug must be reproducible from a
REPL with no fixtures.

The whitelist tests are the load-bearing ones. `test_ineligible_types_name_
real_fields` in particular exists to stop the other two from asserting
vacuously: it proves `User.password` and `AuditLog.before` are REAL fields, so
the whitelist is rejecting genuinely-valid declarations rather than typos.
"""
import dataclasses

import pytest

from apps.prompts import bindings


# ---------------------------------------------------------------------------
# T005 -- FieldBinding is a frozen value
# ---------------------------------------------------------------------------


def test_field_binding_is_frozen():
    b = bindings.FieldBinding("Customer", "name", "{Customer.name}")
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.field_name = "email"


def test_field_binding_is_hashable():
    b = bindings.FieldBinding("Customer", "name", "{Customer.name}")
    assert {b, b} == {b}


def test_field_binding_equality_is_by_value():
    a = bindings.FieldBinding("Customer", "name", "{Customer.name}")
    b = bindings.FieldBinding("Customer", "name", "{Customer.name}")
    c = bindings.FieldBinding("Customer", "age", "{Customer.age}")
    assert a == b
    assert a != c


# ---------------------------------------------------------------------------
# T006 / T007 -- placeholder extraction
# ---------------------------------------------------------------------------


def test_extract_placeholders_returns_record_type_and_field():
    assert bindings.extract_placeholders("Hello {Customer.name}.") == {
        ("Customer", "name")
    }


def test_extract_placeholders_collapses_repeats():
    """The same placeholder twice is one binding, not two."""
    body = "{Customer.name} ... and again {Customer.name}."
    assert bindings.extract_placeholders(body) == {("Customer", "name")}


def test_extract_placeholders_finds_all_distinct():
    body = "{Customer.name} is {Customer.age} with {Policy.premium_usd}."
    assert bindings.extract_placeholders(body) == {
        ("Customer", "name"),
        ("Customer", "age"),
        ("Policy", "premium_usd"),
    }


def test_extract_placeholders_empty_for_plain_text():
    assert bindings.extract_placeholders("No placeholders at all.") == set()


def test_extract_placeholders_treats_double_braces_as_escaped():
    """`{{` / `}}` is a literal brace, following str.format convention."""
    assert bindings.extract_placeholders("Literal {{Customer.name}} braces.") == set()


def test_extract_placeholders_ignores_unqualified_token():
    """
    T007. A bare `{name}` names no record type, and guessing one would be
    ambiguous the moment two eligible types share a field name -- three
    already do (`archived_at` on Customer, Policy and Claim).

    So extraction returns NOTHING for it rather than inventing a record type.
    The token is then an unbound placeholder, which validation rejects
    (FR-007) -- a loud failure rather than a silent wrong guess.
    """
    assert bindings.extract_placeholders("Hello {name}.") == set()


# ---------------------------------------------------------------------------
# T008-T010 -- the whitelist
# ---------------------------------------------------------------------------

APPROVED_RECORD_TYPES = {
    "Customer",
    "Policy",
    "Claim",
    "RiskAssessment",
    "RiskFactor",
}


def test_eligible_record_types_is_exactly_the_approved_five():
    """
    FR-023/FR-024 enforcement point. EQUALITY, not containment, in both
    directions -- the same discipline as
    `apps/risk/tests/test_rules.py::test_factor_set_is_exactly_the_approved_five`:

      - a subset check would let an unapproved SIXTH type through
      - a superset check would let an approved one be silently DROPPED

    The second direction matters even though `RiskFactor` is currently
    declared against by no template: an eligible type must not fall out of the
    approved set merely because nothing uses it today.

    Without this assertion FR-023 lives only in prose (spec Key Entities,
    research.md §3, the bindings.py comment) and nothing fails when someone
    adds `User` to the frozenset.

    If this test fails, do NOT relax it -- amend FR-023 deliberately, or
    remove the offending record type.
    """
    assert bindings.ELIGIBLE_RECORD_TYPES == APPROVED_RECORD_TYPES, (
        "FR-023 violation: the eligible record type set changed. "
        f"Expected exactly {sorted(APPROVED_RECORD_TYPES)}, "
        f"got {sorted(bindings.ELIGIBLE_RECORD_TYPES)}. "
        "Identity, auth and audit types are permanently ineligible (FR-025); "
        "any new type requires amending FR-023 and this test deliberately."
    )


@pytest.mark.parametrize(
    "record_type", ["User", "AuditLog", "Session", "ContentType"]
)
def test_identity_and_audit_types_are_ineligible(record_type):
    """FR-025. These are not business data and can never be declared against."""
    assert record_type not in bindings.ELIGIBLE_RECORD_TYPES


@pytest.mark.django_db
def test_ineligible_types_name_real_fields():
    """
    T010 -- the test that gives T008/T009 their teeth.

    Every field below GENUINELY EXISTS. A validator that only checked field
    existence (FR-006) would admit all of them, because the field really does
    resolve. It is the whitelist (FR-023), not field existence, that rejects
    them.

    Without this assertion the other two whitelist tests could pass while the
    whitelist rejected nothing more than typos, and no one would notice.

    `AuditLog.before`/`.after` is the sharpest case: those JSONFields hold
    prior-state snapshots of OTHER records, so a single approved declaration
    against them would re-expose arbitrary fields of arbitrary record types --
    including the ineligible ones -- through one entry that passes every other
    check.
    """
    from django.contrib.auth import get_user_model

    from apps.audit.models import AuditLog

    User = get_user_model()

    # Real fields on User -- credential hash and authorization state.
    assert User._meta.get_field("password") is not None
    assert User._meta.get_field("is_superuser") is not None
    assert User._meta.get_field("role") is not None

    # Real fields on AuditLog -- arbitrary prior state of other records.
    assert AuditLog._meta.get_field("before") is not None
    assert AuditLog._meta.get_field("after") is not None

    # ... and neither type may be declared against.
    assert "User" not in bindings.ELIGIBLE_RECORD_TYPES
    assert "AuditLog" not in bindings.ELIGIBLE_RECORD_TYPES


# ---------------------------------------------------------------------------
# T073-T074 -- the resolver (declaration -> value)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_resolve_returns_only_declared_fields():
    """
    T074 / FR-020. The resolver's output keys equal the template's declared
    bindings EXACTLY -- nothing outside the declaration appears.

    This is the field-by-field mapping Phase 4b's post-generation validator
    consumes: given generated text and this dict, it can check every claim in
    the text against a value the template was actually permitted to draw on.
    A resolver returning one extra field would silently widen what 4b accepts
    as grounded.
    """
    from apps.customers.factories import CustomerFactory
    from apps.policies.factories import PolicyFactory
    from apps.prompts import library

    customer = CustomerFactory()
    policy = PolicyFactory(customer=customer)

    template = next(
        t
        for t in library.TEMPLATES
        if t.identifier == "personalized_renewal_reminder"
    )

    resolved = bindings.resolve(template, customer=customer, policy=policy)

    assert set(resolved) == set(template.bindings)

    sources = {"Customer": customer, "Policy": policy}
    for binding, value in resolved.items():
        assert value == getattr(sources[binding.record_type], binding.field_name)


@pytest.mark.django_db
def test_resolve_raises_when_a_record_is_missing():
    """
    A binding with no record to resolve against is an error, never a silent
    None -- a None rendered into a prompt would become the literal word
    "None" in generated text, which reads as a fact about the customer.
    """
    from apps.customers.factories import CustomerFactory
    from apps.prompts import library

    template = next(
        t
        for t in library.TEMPLATES
        if t.identifier == "personalized_renewal_reminder"
    )

    with pytest.raises(bindings.UnresolvedBinding):
        bindings.resolve(template, customer=CustomerFactory())


def test_no_renderer_exists():
    """
    FR-019 / research.md §6. Phase 4a stops at the resolver deliberately.

    If a `render` function appears here, 4a has taken on 4b's job -- and it
    would have been designed against an LLM service that does not exist yet.
    """
    assert not hasattr(bindings, "render")
