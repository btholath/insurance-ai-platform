"""
Registry tests (T028).

These cover the registry as a mechanism -- resolution, per-module role
sets, and the guarantee that an unregistered path is audited by nobody.
The end-to-end refusal behaviour it drives is covered by
apps/customers/tests/test_audit.py and apps/policies/tests/test_audit.py.
"""
import pytest

from apps.accounts.models import Role
from apps.core import audit_routes
from apps.core.audit_routes import AuditedRoute

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def test_unregistered_path_matches_nothing():
    """
    The precondition for FR-032 at the registry layer: a path no module
    claims produces no entry at all, rather than falling back to some
    default module and mislabelling the target type.

    This used /api/risk/1/ as its unregistered example until Phase 3a
    registered risk as the registry's fourth consumer -- exactly the
    predicted swap T082 called out, following the identical swap Phase 2c
    made for /api/claims/1/. The example was swapped rather than the
    assertion weakened -- the guarantee under test is unchanged, only the
    set of paths that demonstrate it.
    """
    assert audit_routes.match("/api/fraud/1/") is None
    assert audit_routes.match("/health/") is None
    assert audit_routes.match("/") is None


def test_registered_prefixes_resolve_to_their_own_target_type():
    customers = audit_routes.match("/api/customers/42/")
    policies = audit_routes.match("/api/policies/42/")
    risk = audit_routes.match("/api/risk/42/")

    assert customers.target_type == "customers.Customer"
    assert customers.action_prefix == "customer"
    assert policies.target_type == "policies.Policy"
    assert policies.action_prefix == "policy"
    assert risk.target_type == "risk.RiskAssessment"
    assert risk.action_prefix == "risk"


def test_collection_and_detail_paths_resolve_to_the_same_entry():
    assert audit_routes.match("/api/policies/") is audit_routes.match("/api/policies/7/")


def test_longest_prefix_wins_regardless_of_registration_order():
    """
    A more specific entry must shadow a broader one even when registered
    first, otherwise which entry matches is an accident of import order.
    """
    specific = AuditedRoute(
        prefix="/api/policies/special/",
        target_type="policies.Special",
        action_prefix="special",
        view_roles=(Role.UNDERWRITER,),
        write_roles=(Role.UNDERWRITER,),
    )
    audit_routes.register(specific)
    try:
        assert audit_routes.match("/api/policies/special/1/").target_type == "policies.Special"
        assert audit_routes.match("/api/policies/1/").target_type == "policies.Policy"
    finally:
        audit_routes._REGISTRY.remove(specific)


def test_register_replaces_an_entry_with_the_same_prefix():
    """Re-registration must not leave two entries competing for one prefix."""
    original = audit_routes.match("/api/policies/")
    replacement = original._replace(action_prefix="replaced")

    audit_routes.register(replacement)
    try:
        matches = [e for e in audit_routes.all_routes() if e.prefix == "/api/policies/"]
        assert len(matches) == 1
        assert audit_routes.match("/api/policies/").action_prefix == "replaced"
    finally:
        audit_routes.register(original)

    assert audit_routes.match("/api/policies/").action_prefix == "policy"


# ---------------------------------------------------------------------------
# Per-module role sets -- the load-bearing difference
# ---------------------------------------------------------------------------


def test_role_sets_differ_per_module():
    """
    The registry's reason for existing. A Product Manager may read
    policies but not customers, so a platform-wide role set would record
    one of those two wrongly.
    """
    customers = audit_routes.match("/api/customers/")
    policies = audit_routes.match("/api/policies/")

    assert Role.PRODUCT_MANAGER not in customers.view_roles
    assert Role.PRODUCT_MANAGER in policies.view_roles

    # Write access is reversed between the two modules.
    assert Role.CUSTOMER_SERVICE in customers.write_roles
    assert Role.CUSTOMER_SERVICE not in policies.write_roles
    assert Role.UNDERWRITER in policies.write_roles
    assert Role.UNDERWRITER not in customers.write_roles


def test_executive_leadership_reads_neither_module():
    for prefix in ("/api/customers/", "/api/policies/"):
        assert Role.EXECUTIVE_LEADERSHIP not in audit_routes.match(prefix).view_roles


def test_customer_role_sets_match_the_shipped_viewset():
    """
    Pins the Phase 2a values the handler used to hardcode. If
    apps.customers.views and the registry ever disagree, customer refusal
    recording has silently changed.
    """
    from apps.customers.views import VIEW_ROLES, WRITE_ROLES

    entry = audit_routes.match("/api/customers/")
    assert set(entry.view_roles) == set(VIEW_ROLES)
    assert set(entry.write_roles) == set(WRITE_ROLES)


def test_risk_role_sets_match_the_shipped_viewset():
    """
    Pins Phase 3a's values against apps.risk.views, the same way T118
    (nee test_customer_role_sets_match_the_shipped_viewset) pins
    customers. If the two ever disagree, risk refusal recording has
    silently changed.
    """
    from apps.risk.views import RECOMPUTE_ROLES, VIEW_ROLES

    entry = audit_routes.match("/api/risk/")
    assert set(entry.view_roles) == set(VIEW_ROLES)
    assert set(entry.write_roles) == set(RECOMPUTE_ROLES)


def test_risk_view_roles_are_the_five_role_shape():
    """
    A fourth distinct role shape against Customer's seven, Policy's eight
    and Claim's five (contracts/risk-assessment-api.md).
    """
    entry = audit_routes.match("/api/risk/")

    assert set(entry.view_roles) == {
        Role.RISK_MANAGER,
        Role.UNDERWRITER,
        Role.FRAUD_ANALYST,
        Role.COMPLIANCE_OFFICER,
        Role.SYSTEM_ADMINISTRATOR,
    }
    assert Role.CUSTOMER_SERVICE not in entry.view_roles


def test_roles_for_selects_write_roles_on_write_methods():
    entry = audit_routes.match("/api/policies/")

    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert audit_routes.roles_for(entry, method) == entry.write_roles
    for method in ("GET", "HEAD", "OPTIONS"):
        assert audit_routes.roles_for(entry, method) == entry.view_roles


# ---------------------------------------------------------------------------
# Action naming
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,expected",
    [
        ("GET", "policy.viewed"),
        ("HEAD", "policy.viewed"),
        ("OPTIONS", "policy.viewed"),
        ("POST", "policy.created"),
        ("PUT", "policy.updated"),
        ("PATCH", "policy.updated"),
        ("DELETE", "policy.deleted"),
    ],
)
def test_action_names_derive_from_the_matched_entry(method, expected):
    assert audit_routes.action_for(audit_routes.match("/api/policies/"), method) == expected


def test_unknown_method_falls_back_without_raising():
    entry = audit_routes.match("/api/customers/")
    assert audit_routes.action_for(entry, "TRACE") == "customer.accessed"


def test_customer_actions_keep_their_phase_2a_names():
    """The exact strings the shipped handler wrote, now derived."""
    entry = audit_routes.match("/api/customers/")
    assert audit_routes.action_for(entry, "GET") == "customer.viewed"
    assert audit_routes.action_for(entry, "POST") == "customer.created"
    assert audit_routes.action_for(entry, "PATCH") == "customer.updated"
    assert audit_routes.action_for(entry, "DELETE") == "customer.deleted"
