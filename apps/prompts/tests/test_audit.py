"""
The prompt library as the audited-route registry's FIFTH consumer
(T038-T040, US3).

FR-013's claim is that a new module joins the registry as configuration
rather than as another branch in the refusal handler. These tests are what
make that claim checkable: the entry exists, it carries this module's own
action names and target type, and the four existing entries are untouched.

`test_successful_read_writes_no_audit_row` is the deliberate one -- see its
docstring.
"""
import pytest

from apps.accounts.models import Role
from apps.audit.models import AuditLog
from apps.core import audit_routes

LIST_URL = "/api/prompts/templates/"
DETAIL_URL = "/api/prompts/templates/risk_assessment_summary/"


@pytest.mark.django_db
def test_refusal_is_recorded_under_this_modules_action_and_target(api_client):
    """
    FR-015. An unauthenticated read is a refusal, recorded automatically by
    apps/core/exception_handlers.py -- no per-module code.

    THE ACTION PREFIX IS THE ASSERTION THAT MATTERS. `prompt.viewed`, not
    `customer.viewed`. If /api/prompts/ were ever nested under an existing
    prefix, match() would return that module's entry and every prompt refusal
    would be audited against the wrong module's role set -- the precise
    failure apps/risk/urls.py's top-level mount exists to avoid, and one that
    is invisible from the response.
    """
    before = AuditLog.objects.filter(target_type="prompts.PromptTemplate").count()

    api_client.get(LIST_URL)

    rows = AuditLog.objects.filter(target_type="prompts.PromptTemplate")
    assert rows.count() == before + 1

    row = rows.order_by("-timestamp").first()
    assert row.action == "prompt.viewed"
    assert row.target_type == "prompts.PromptTemplate"
    assert row.outcome == "refused"
    assert row.actor is None
    assert row.context["path"] == LIST_URL


@pytest.mark.django_db
def test_successful_read_writes_no_audit_row(authenticated_client):
    """
    FR-015 AS NARROWED DURING PLANNING (research.md §7, plan.md Complexity
    Tracking). This is DELIBERATE and must not be "fixed".

    FR-015 originally read "every access -- successful or refused". Verified
    against the codebase: NO module on this platform audits successful reads.
    apps/risk/views.py contains zero record_action calls; customers, policies
    and claims audit create/update/destroy only. Refusals are audited
    centrally for every module.

    Implementing the literal wording would make the prompt library the only
    module writing an audit row per GET -- contradicting FR-013/FR-014's
    premise that it behaves as the registry's fifth consumer, and SC-006's
    requirement that existing behaviour is unaffected. A template read also
    discloses no customer data, so the compliance value would be nil against
    real row volume.

    If auditing successful reads is ever wanted, it is a platform-wide change
    for all five modules and belongs in its own spec.
    """
    client, _user = authenticated_client(Role.RISK_MANAGER)
    before = AuditLog.objects.filter(target_type="prompts.PromptTemplate").count()

    assert client.get(LIST_URL).status_code == 200
    assert client.get(DETAIL_URL).status_code == 200

    after = AuditLog.objects.filter(target_type="prompts.PromptTemplate").count()
    assert after == before, (
        "a successful prompt library read wrote an audit row; no other module "
        "on this platform does that (FR-015 as narrowed, research.md §7)"
    )


def test_registry_has_five_entries_and_prompts_has_the_ninth_view_role():
    """
    FR-013 / FR-014 / SC-006. The fifth consumer exists AND the four that
    came before it are byte-for-byte what they were.

    The role-set SIZES are asserted, not just presence: 7/2, 8/2, 5/2, 5/2 are
    four distinct deliberate shapes, and this feature adding a fifth must not
    have perturbed any of them.
    """
    routes = {r.prefix: r for r in audit_routes.all_routes()}

    assert set(routes) == {
        "/api/customers/",
        "/api/policies/",
        "/api/claims/",
        "/api/risk/",
        "/api/prompts/",
    }

    # The four pre-existing entries, unchanged.
    existing = {
        "/api/customers/": ("customers.Customer", 7, 2),
        "/api/policies/": ("policies.Policy", 8, 2),
        "/api/claims/": ("claims.Claim", 5, 2),
        "/api/risk/": ("risk.RiskAssessment", 5, 2),
    }
    for prefix, (target_type, n_view, n_write) in existing.items():
        route = routes[prefix]
        assert route.target_type == target_type
        assert len(route.view_roles) == n_view
        assert len(route.write_roles) == n_write

    # The new one: the platform's first universal view set and first
    # single-role write set.
    prompts = routes["/api/prompts/"]
    assert prompts.target_type == "prompts.PromptTemplate"
    assert prompts.action_prefix == "prompt"
    assert len(prompts.view_roles) == 9
    assert set(prompts.view_roles) == {r.value for r in Role}
    assert prompts.write_roles == (Role.SYSTEM_ADMINISTRATOR,)

    # Executive Leadership specifically -- absent from all four existing view
    # sets, present here. The proof this set was reasoned about.
    assert Role.EXECUTIVE_LEADERSHIP in prompts.view_roles
    for prefix in existing:
        assert Role.EXECUTIVE_LEADERSHIP not in routes[prefix].view_roles
