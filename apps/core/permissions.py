"""
The platform's single reusable RBAC mechanism (FR-015).

HasRole(*roles) is a permission-class factory: it returns a DRF permission
class bound to the given set of allowed roles, used as
    permission_classes = [HasRole(Role.SYSTEM_ADMINISTRATOR)]

Design decisions (research.md §4), enforced here rather than left to callers:

1. Superuser does not bypass. Only request.user.role is checked — never
   request.user.is_superuser. The System Administrator role is not an
   unrestricted bypass (spec edge case).
2. Deny by default (FR-014). A null/blank/unrecognised role fails every
   check; the check is membership in the allowed set, never a negative
   check on a specific disallowed value.
3. Existence non-disclosure (FR-012). On detail views (object-level
   permission checks), an unauthenticated or unpermitted caller raises
   NotFound (404) rather than returning False (which DRF would turn into
   403) — a 403 on a detail route would confirm the record exists.
   Collection-route (view-level) denials return the normal 403.

   DRF calls has_permission() in APIView.initial(), before the handler
   method runs — for every route, detail or collection — and a False
   there short-circuits straight to a 403/401 without ever reaching
   get_object()/has_object_permission(). So has_permission() must defer
   to the object-level check on detail routes (identified by a lookup
   kwarg — e.g. "pk" — being present in view.kwargs) rather than deny
   outright; only has_object_permission() is allowed to raise the 404
   for those routes. Collection routes have no lookup kwarg, so
   has_permission() remains the sole, authoritative check there.
4. Immediate effect (FR-016). request.user.role is read fresh from the
   database on every request; nothing here caches a role across requests.
"""
from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission


def HasRole(*roles):
    allowed = {getattr(role, "value", role) for role in roles}

    class _HasRole(BasePermission):
        def _is_detail_route(self, view):
            lookup_kwarg = getattr(view, "lookup_url_kwarg", None) or getattr(view, "lookup_field", None)
            return bool(lookup_kwarg) and lookup_kwarg in getattr(view, "kwargs", {})

        def has_permission(self, request, view):
            if self._is_detail_route(view):
                return True

            user = request.user
            if not user or not user.is_authenticated:
                return False
            return getattr(user, "role", None) in allowed

        def has_object_permission(self, request, view, obj):
            user = request.user
            if not user or not user.is_authenticated or getattr(user, "role", None) not in allowed:
                raise NotFound()
            return True

    _HasRole.__name__ = "HasRole"
    return _HasRole
