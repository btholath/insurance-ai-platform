"""
The audited-route registry (FR-031, FR-032).

Phase 2a's refusal handler hardcoded customer knowledge in four places: the
route prefix, the target type, the action names, and the role sets it
consulted to tell a refusal from an ordinary miss. FR-031 needs the same
behaviour for policies and Claims will need it a third time, so the
knowledge moves out of the handler and becomes configuration.

The role sets are deliberately PER MODULE rather than platform-wide, and
that is the load-bearing part. A Product Manager may read policies but not
customers, so their 404 on a missing policy is an ordinary miss while the
same user's 404 on a missing customer is a refusal. A single shared role
set would necessarily record one of those two wrongly.

Entries are registered at app-ready rather than import time: this module is
reachable from settings (the handler is named in REST_FRAMEWORK), and
importing views at that point would trigger app loading before the registry
is ready.
"""
from collections import namedtuple

AuditedRoute = namedtuple(
    "AuditedRoute",
    "prefix target_type action_prefix view_roles write_roles",
)

_REGISTRY = []

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Suffix per HTTP method, so a refusal is legible in the trail. The
# action_prefix from the matched entry supplies the module half.
_METHOD_ACTION_SUFFIXES = {
    "GET": "viewed",
    "HEAD": "viewed",
    "OPTIONS": "viewed",
    "POST": "created",
    "PUT": "updated",
    "PATCH": "updated",
    "DELETE": "deleted",
}

_FALLBACK_ACTION_SUFFIX = "accessed"


def register(route):
    """Add an entry, replacing any existing entry with the same prefix.

    Replacing rather than appending keeps app-ready registration
    idempotent -- Django may import an AppConfig's ready() more than once
    in some test and autoreload paths, and a duplicated entry would make
    which one matches an accident of ordering.
    """
    _REGISTRY[:] = [entry for entry in _REGISTRY if entry.prefix != route.prefix]
    _REGISTRY.append(route)
    return route


def all_routes():
    return tuple(_REGISTRY)


def match(path):
    """The entry whose prefix this path falls under, or None.

    Longest prefix wins, so a more specific entry can shadow a broader one
    regardless of registration order.
    """
    candidates = [entry for entry in _REGISTRY if path.startswith(entry.prefix)]
    if not candidates:
        return None
    return max(candidates, key=lambda entry: len(entry.prefix))


def method_is_write(method):
    return method in _WRITE_METHODS


def action_for(route, method):
    suffix = _METHOD_ACTION_SUFFIXES.get(method, _FALLBACK_ACTION_SUFFIX)
    return f"{route.action_prefix}.{suffix}"


def roles_for(route, method):
    """The role set that decides refusal-vs-miss for this method."""
    return route.write_roles if method_is_write(method) else route.view_roles


def register_defaults():
    """Register the shipped modules. Called from AppConfig.ready().

    Imported lazily inside the function for the reason in the module
    docstring: at import time the app registry is not yet populated.
    """
    from apps.accounts.models import Role

    register(
        AuditedRoute(
            prefix="/api/customers/",
            target_type="customers.Customer",
            action_prefix="customer",
            # Exactly the seven view / two write roles the Phase 2a handler
            # consulted, mirrored from apps.customers.views. Product Manager
            # and Executive Leadership are absent by design.
            view_roles=(
                Role.CUSTOMER_SERVICE,
                Role.SYSTEM_ADMINISTRATOR,
                Role.UNDERWRITER,
                Role.CLAIMS_ADJUSTER,
                Role.FRAUD_ANALYST,
                Role.RISK_MANAGER,
                Role.COMPLIANCE_OFFICER,
            ),
            write_roles=(Role.CUSTOMER_SERVICE, Role.SYSTEM_ADMINISTRATOR),
        )
    )

    register(
        AuditedRoute(
            prefix="/api/policies/",
            target_type="policies.Policy",
            action_prefix="policy",
            # Eight view roles -- everyone except Executive Leadership.
            # Product Manager reads policies though they may not read
            # customers: product mix is a product concern, personal data is
            # not.
            view_roles=(
                Role.CUSTOMER_SERVICE,
                Role.SYSTEM_ADMINISTRATOR,
                Role.UNDERWRITER,
                Role.CLAIMS_ADJUSTER,
                Role.FRAUD_ANALYST,
                Role.RISK_MANAGER,
                Role.COMPLIANCE_OFFICER,
                Role.PRODUCT_MANAGER,
            ),
            # Underwriter, not Customer Service: writing policy terms is
            # underwriting work. This is the reverse of the customer module.
            write_roles=(Role.UNDERWRITER, Role.SYSTEM_ADMINISTRATOR),
        )
    )

    register(
        AuditedRoute(
            prefix="/api/claims/",
            target_type="claims.Claim",
            action_prefix="claim",
            # FIVE view roles -- the narrowest read set of the three
            # modules, against Customer's seven and Policy's eight. Claim
            # amounts are financial detail about an individual, so
            # product- and sales-facing roles are excluded entirely:
            # Customer Service, Underwriter, Product Manager and Executive
            # Leadership have no record-level claim access.
            #
            # The sharp case this entry exists to get right: an
            # Underwriter may WRITE policies but may not READ claims, so
            # their 404 on a claim is a REFUSAL while the same user's 404
            # on a policy is an ordinary miss. Only per-module role sets
            # can tell those apart.
            view_roles=(
                Role.CLAIMS_ADJUSTER,
                Role.FRAUD_ANALYST,
                Role.COMPLIANCE_OFFICER,
                Role.RISK_MANAGER,
                Role.SYSTEM_ADMINISTRATOR,
            ),
            # Two write roles -- a third distinct write set, after
            # Customer's (Customer Service) and Policy's (Underwriter). A
            # Fraud Analyst investigates claims but does not adjudicate
            # them, so they read without writing.
            write_roles=(Role.CLAIMS_ADJUSTER, Role.SYSTEM_ADMINISTRATOR),
        )
    )
    # The anomaly routes at /api/claims/anomalies/ need NO second entry:
    # match() selects the longest matching prefix, they are nested under
    # this one, and they share its role sets exactly (FR-047). If anomalies
    # ever diverge in roles, a second entry is the mechanism -- that is the
    # registry working as designed, not a workaround.

    register(
        AuditedRoute(
            prefix="/api/risk/",
            target_type="risk.RiskAssessment",
            action_prefix="risk",
            # FIVE view roles -- a fourth distinct shape against Customer's
            # seven, Policy's eight and Claim's five. Customer Service reads
            # customers but not their risk assessments: a risk assessment is
            # a judgment about a person, more sensitive than the customer
            # record it derives from (contracts/risk-assessment-api.md).
            view_roles=(
                Role.RISK_MANAGER,
                Role.UNDERWRITER,
                Role.FRAUD_ANALYST,
                Role.COMPLIANCE_OFFICER,
                Role.SYSTEM_ADMINISTRATOR,
            ),
            # Two write roles. The only write route is recompute; an
            # Underwriter may read but not trigger one (FR-043).
            write_roles=(Role.RISK_MANAGER, Role.SYSTEM_ADMINISTRATOR),
        )
    )
