"""
The grounding contract, enforced (T016-T022, US1).

This is the module that makes a class of mistake impossible rather than
merely unlikely. Each rejection path below corresponds to a way a template
could otherwise ship a declaration that disagrees with what its body actually
does -- and every one of those would hand Phase 4b's post-generation
validator the wrong thing to check against.

`test_declared_record_type_must_be_eligible` is the sharpest of them: every
field it tries GENUINELY EXISTS, so field-existence checking alone would admit
all of them. It asserts on the error MESSAGE, not just the exception type,
because a "no such field" message there would mean the whitelist was not what
rejected it.
"""
import pytest

from apps.prompts import validation
from apps.prompts.bindings import FieldBinding


def _template(identifier="t", body="Hi {Customer.name}.", bindings=None):
    """
    A minimal template-shaped object.

    Deliberately NOT importing the real PromptTemplate: US1's validation must
    be exercisable before US4 authors any real template, and these tests
    construct their own fixtures precisely so the two phases stay independent.
    """
    if bindings is None:
        bindings = (FieldBinding("Customer", "name", "{Customer.name}"),)
    return validation.TemplateShape(
        identifier=identifier, body=body, bindings=tuple(bindings)
    )


# ---------------------------------------------------------------------------
# T016 -- FR-005, both directions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_undeclared_reference_is_rejected():
    """A body referencing a field its declaration omits."""
    t = _template(
        body="Hi {Customer.name}, you are {Customer.age}.",
        bindings=[FieldBinding("Customer", "name", "{Customer.name}")],
    )
    with pytest.raises(validation.LibraryError) as exc:
        validation.check_template(t)
    assert "age" in str(exc.value)


@pytest.mark.django_db
def test_unused_declaration_is_rejected():
    """
    The other direction, and the one easier to overlook. A stale declared
    field nothing references would silently WIDEN what Phase 4b's validator
    accepts -- the same failure as an undeclared reference, in reverse.
    """
    t = _template(
        body="Hi {Customer.name}.",
        bindings=[
            FieldBinding("Customer", "name", "{Customer.name}"),
            FieldBinding("Customer", "age", "{Customer.age}"),
        ],
    )
    with pytest.raises(validation.LibraryError) as exc:
        validation.check_template(t)
    assert "age" in str(exc.value)


@pytest.mark.django_db
def test_exact_agreement_passes():
    validation.check_template(_template())


# ---------------------------------------------------------------------------
# T017 -- FR-006, field existence
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_declared_field_must_exist_on_model():
    """
    Also the spec's 'renamed or removed by a future migration' edge case: a
    dangling declaration fails loudly at validation time rather than becoming
    a field Phase 4b's validator can never resolve.
    """
    t = _template(
        body="Hi {Customer.no_such_field}.",
        bindings=[
            FieldBinding("Customer", "no_such_field", "{Customer.no_such_field}")
        ],
    )
    with pytest.raises(validation.LibraryError) as exc:
        validation.check_template(t)
    assert "no_such_field" in str(exc.value)


# ---------------------------------------------------------------------------
# T018 -- FR-023/FR-025, eligibility (NOT existence)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "record_type,field_name",
    [
        ("User", "password"),
        ("User", "is_superuser"),
        ("User", "role"),
        ("AuditLog", "before"),
        ("AuditLog", "after"),
    ],
)
def test_declared_record_type_must_be_eligible(record_type, field_name):
    """
    Every field here EXISTS. FR-004-008 alone would admit all of them.

    The assertion on the message is the point: the error must identify the
    RECORD TYPE as ineligible. A "no such field" message would mean field
    existence rejected it by accident and the whitelist is not actually
    wired -- which would leave `AuditLog.before` (arbitrary prior state of
    arbitrary records) reachable the moment someone declared a field that
    happens to resolve.
    """
    placeholder = "{%s.%s}" % (record_type, field_name)
    b = FieldBinding(record_type, field_name, placeholder)
    with pytest.raises(validation.LibraryError) as exc:
        validation.check_binding(b)
    message = str(exc.value)
    assert record_type in message
    assert "not eligible" in message.lower()
    # And specifically NOT rejected for the wrong reason:
    assert "no such field" not in message.lower()


@pytest.mark.django_db
def test_eligible_type_with_real_field_passes():
    validation.check_binding(FieldBinding("Customer", "name", "{Customer.name}"))


# ---------------------------------------------------------------------------
# T019 -- FR-007, unbound placeholders
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unqualified_placeholder_is_rejected():
    """
    A bare `{name}` extracts to nothing (bindings.py), so the declared field
    it was meant to bind has no matching placeholder -- caught as an unused
    declaration. Either way it is a loud failure, never a silent guess.
    """
    t = _template(
        body="Hi {name}.",
        bindings=[FieldBinding("Customer", "name", "{Customer.name}")],
    )
    with pytest.raises(validation.LibraryError):
        validation.check_template(t)


@pytest.mark.django_db
def test_placeholder_with_no_binding_at_all_is_rejected():
    t = _template(body="Hi {Customer.name} and {Policy.premium_usd}.")
    with pytest.raises(validation.LibraryError) as exc:
        validation.check_template(t)
    assert "premium_usd" in str(exc.value)


# ---------------------------------------------------------------------------
# T020 -- FR-001, identifier uniqueness
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_duplicate_identifier_is_rejected():
    """
    A later audit record naming a duplicated identifier would be ambiguous
    about which template produced the output.
    """
    a = _template(identifier="same")
    b = _template(identifier="same")
    with pytest.raises(validation.LibraryError) as exc:
        validation.validate_library((a, b))
    assert "same" in str(exc.value)


# ---------------------------------------------------------------------------
# T021 -- FR-008, all-or-nothing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_library_validation_is_all_or_nothing():
    """
    One invalid template among valid ones fails the WHOLE library. There is
    no 'skip the bad one and continue' path -- a partially-valid library
    would mean some templates carry an enforced contract and others carry an
    unchecked one, with nothing marking which is which.
    """
    good = _template(identifier="good")
    bad = _template(
        identifier="bad",
        body="Hi {Customer.nope}.",
        bindings=[FieldBinding("Customer", "nope", "{Customer.nope}")],
    )
    with pytest.raises(validation.LibraryError) as exc:
        validation.validate_library((good, bad))
    assert "bad" in str(exc.value)


@pytest.mark.django_db
def test_all_valid_library_passes():
    validation.validate_library(
        (_template(identifier="one"), _template(identifier="two"))
    )


def test_empty_library_is_vacuously_valid():
    """
    Boundary behaviour, defined rather than accidental. Unreachable in
    practice (the real library is pinned at exactly seven) but the function
    should not raise on an empty input.
    """
    validation.validate_library(())


# ---------------------------------------------------------------------------
# T022 -- no database needed
# ---------------------------------------------------------------------------


def test_validation_needs_no_database():
    """
    Deliberately WITHOUT @pytest.mark.django_db.

    Field-existence checking reads model METADATA (`_meta.get_field`), never a
    row. If this test ever fails with a database access error, validation has
    started querying -- which would mean the grounding contract depends on
    data rather than on schema, and could pass or fail depending on what
    happens to be in the database.
    """
    validation.check_binding(FieldBinding("Customer", "name", "{Customer.name}"))
    validation.check_template(_template())

    with pytest.raises(validation.LibraryError):
        validation.check_binding(FieldBinding("User", "password", "{User.password}"))
