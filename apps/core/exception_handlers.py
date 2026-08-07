"""
Refusal auditing (FR-030).

Phase 1 recorded successes only. HasRole denies in two different shapes --
collection routes return False from has_permission() (which DRF turns into
403/401 inside APIView.initial()), while detail routes raise NotFound from
has_object_permission() for existence non-disclosure. Both surface here as
exceptions, so one handler catches both. Putting the write inside HasRole
instead would miss the False path and would change a Phase 1 mechanism
shared by every module.

The response is never altered -- the entry is written server-side, so
FR-022 non-disclosure survives refusal logging.
"""
from rest_framework.exceptions import NotAuthenticated, NotFound, PermissionDenied
from rest_framework.views import exception_handler as drf_exception_handler

from apps.audit.services import record_action

# Actions recorded per HTTP method, so a refusal is legible in the trail.
_METHOD_ACTIONS = {
    "GET": "customer.viewed",
    "HEAD": "customer.viewed",
    "OPTIONS": "customer.viewed",
    "POST": "customer.created",
    "PUT": "customer.updated",
    "PATCH": "customer.updated",
    "DELETE": "customer.deleted",
}


def audited_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is not None and isinstance(exc, (PermissionDenied, NotAuthenticated, NotFound)):
        request = context.get("request")
        if request is not None and _is_customer_route(request) and _is_refusal(request, exc):
            _record_refusal(request, context)

    return response


def _is_customer_route(request):
    return request.path.startswith("/api/customers/")


def _is_refusal(request, exc):
    """
    Distinguish a permission refusal from an ordinary miss.

    A detail route raises NotFound both when a permitted user asks for a
    customer that does not exist and when an unpermitted user is refused.
    The exception alone cannot tell them apart, so consult the requester's
    role: an unauthenticated user, or one outside the FR-024 view set, is a
    refusal. A permitted user's NotFound is a genuine miss and is not
    logged -- otherwise every mistyped reference would be recorded as a
    permission refusal and the compliance record would be noise.
    """
    if isinstance(exc, (PermissionDenied, NotAuthenticated)):
        return True

    # Imported lazily: this module is imported from settings, and importing
    # views at that point would trigger app loading before the registry is
    # ready.
    from apps.customers.views import VIEW_ROLES, WRITE_ACTIONS, WRITE_ROLES

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return True

    role = getattr(user, "role", None)
    allowed = WRITE_ROLES if _method_is_write(request) else VIEW_ROLES
    return role not in {getattr(r, "value", r) for r in allowed}


def _method_is_write(request):
    return request.method in ("POST", "PUT", "PATCH", "DELETE")


def _record_refusal(request, context):
    user = getattr(request, "user", None)
    actor = user if (user is not None and user.is_authenticated) else None

    view = context.get("view")
    target_id = ""
    if view is not None:
        kwargs = getattr(view, "kwargs", {}) or {}
        target_id = kwargs.get("pk") or kwargs.get("id") or ""

    record_action(
        actor=actor,
        action=_METHOD_ACTIONS.get(request.method, "customer.accessed"),
        target_type="customers.Customer",
        target_id=target_id,
        outcome="refused",
        before=None,
        after=None,
        context={"path": request.path, "method": request.method},
    )
