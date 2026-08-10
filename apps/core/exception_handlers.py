"""
Refusal auditing (FR-031, FR-032).

Phase 1 recorded successes only. HasRole denies in two different shapes --
collection routes return False from has_permission() (which DRF turns into
403/401 inside APIView.initial()), while detail routes raise NotFound from
has_object_permission() for existence non-disclosure. Both surface here as
exceptions, so one handler catches both. Putting the write inside HasRole
instead would miss the False path and would change a Phase 1 mechanism
shared by every module.

The response is never altered -- the entry is written server-side, so
existence non-disclosure survives refusal logging.

This handler carries no per-module knowledge. The route prefix, target
type, action names, and the role sets that separate a refusal from an
ordinary miss all come from apps.core.audit_routes, so a new module is
registered as configuration rather than added as another branch here.
"""
from django.http import Http404
from rest_framework.exceptions import NotAuthenticated, NotFound, PermissionDenied
from rest_framework.views import exception_handler as drf_exception_handler

from apps.audit.services import record_action
from apps.core import audit_routes

# Http404 is included deliberately. DRF's get_object() calls Django's
# get_object_or_404, which raises Http404 -- NOT rest_framework's NotFound.
# DRF renders both as a 404, so the two are indistinguishable to a caller,
# but an isinstance check covering only NotFound silently misses every
# refusal that arrives by the get_object() path: an unpermitted user
# asking for an id that does not exist would go unrecorded, which is
# exactly the case FR-031 covers.
_REFUSAL_EXCEPTIONS = (PermissionDenied, NotAuthenticated, NotFound, Http404)


def audited_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if response is not None and isinstance(exc, _REFUSAL_EXCEPTIONS):
        request = context.get("request")
        if request is not None:
            route = audit_routes.match(request.path)
            if route is not None and _is_refusal(request, exc, route):
                _record_refusal(request, context, route)

    return response


def _is_refusal(request, exc, route):
    """
    Distinguish a permission refusal from an ordinary miss.

    A detail route 404s both when a permitted user asks for a record that
    does not exist and when an unpermitted user is refused (whether that
    arrives as NotFound from has_object_permission or as Http404 from
    get_object). The exception alone cannot tell them apart, so consult
    the requester's role against the role set registered for THIS module: an
    unauthenticated user, or one outside that set, is a refusal. A
    permitted user's NotFound is a genuine miss and is not logged --
    otherwise every mistyped reference would be recorded as a permission
    refusal and the compliance record would be noise.

    The role set is per module, which is what makes the Product Manager
    case correct in both directions: permitted on policies (their 404 is a
    miss), not permitted on customers (their 404 is a refusal).
    """
    if isinstance(exc, (PermissionDenied, NotAuthenticated)):
        return True

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return True

    role = getattr(user, "role", None)
    allowed = audit_routes.roles_for(route, request.method)
    return role not in {getattr(r, "value", r) for r in allowed}


def _record_refusal(request, context, route):
    user = getattr(request, "user", None)
    actor = user if (user is not None and user.is_authenticated) else None

    view = context.get("view")
    target_id = ""
    if view is not None:
        kwargs = getattr(view, "kwargs", {}) or {}
        target_id = kwargs.get("pk") or kwargs.get("id") or ""

    record_action(
        actor=actor,
        action=audit_routes.action_for(route, request.method),
        target_type=route.target_type,
        target_id=target_id,
        outcome="refused",
        before=None,
        after=None,
        context={"path": request.path, "method": request.method},
    )
