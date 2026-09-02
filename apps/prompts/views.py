"""
Prompt library API (T045-T046, US3).

THE VIEW SET IS UNIVERSAL, AND THAT IS THE DELIBERATE PART.

All nine roles read, against Customer's 7, Policy's 8, Claim's 5 and Risk's 5.
Every one of those four sets exists to protect an individual's data. A prompt
template holds field NAMES, never field VALUES -- it describes what a future
narrative may draw on and discloses nothing about any customer. There is no
individual here to protect, so narrowing the set would be copying the shape of
the other modules without their reason.

Executive Leadership is the proof this was reasoned about rather than
pattern-matched: absent from all four existing view sets, present here.

Write is System Administrator alone -- also a first, since every existing
module pairs a business role with Sysadmin. Prompt templates are
administrative configuration (BRD Module 12 lists them beside Users, Roles
and Permissions); no business role owns them the way an Underwriter owns
policy terms, so pairing one in for symmetry would be inventing an owner.

Phase 4a is READ-ONLY. The library is code-resident, so there is no create,
update or destroy route. WRITE_ROLES is still declared because the audited
route entry needs it to classify a write-method refusal.
"""
from rest_framework import mixins, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.core.permissions import HasRole

from . import library
from .serializers import (
    PromptTemplateDetailSerializer,
    PromptTemplateListSerializer,
)

VIEW_ROLES = (
    Role.CUSTOMER_SERVICE,
    Role.SYSTEM_ADMINISTRATOR,
    Role.UNDERWRITER,
    Role.CLAIMS_ADJUSTER,
    Role.FRAUD_ANALYST,
    Role.RISK_MANAGER,
    Role.COMPLIANCE_OFFICER,
    Role.PRODUCT_MANAGER,
    Role.EXECUTIVE_LEADERSHIP,
)

WRITE_ROLES = (Role.SYSTEM_ADMINISTRATOR,)


class PromptTemplateViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    Read-only, served entirely from `library.TEMPLATES`.

    No `queryset`: there is no table. `lookup_field = "identifier"` is what
    HasRole's `_is_detail_route()` reads to decide whether a denial should be
    a 403 or an existence-non-disclosing 404 -- it consults
    `lookup_url_kwarg or lookup_field`, so a non-pk lookup works unchanged
    (apps/core/permissions.py:42-44).
    """

    lookup_field = "identifier"
    # Slugs, not integers -- the default pk pattern would not match.
    lookup_value_regex = r"[a-z0-9_]+"

    def get_permissions(self):
        return [HasRole(*VIEW_ROLES)()]

    # No get_queryset(). Both `list` and `retrieve` are overridden below and
    # `get_object` reads the library directly, so nothing would ever call it
    # -- a stub returning TEMPLATES would be dead code implying a database
    # path that does not exist.

    def list(self, request, *args, **kwargs):
        serializer = PromptTemplateListSerializer(library.TEMPLATES, many=True)
        return Response(
            {
                "library_version": library.PROMPT_LIBRARY_VERSION,
                "count": len(library.TEMPLATES),
                "results": serializer.data,
            }
        )

    def get_object(self):
        identifier = self.kwargs.get(self.lookup_field)
        for template in library.TEMPLATES:
            if template.identifier == identifier:
                # Runs the object-level permission check, which is what
                # raises NotFound for an unpermitted caller rather than
                # confirming the template exists.
                self.check_object_permissions(self.request, template)
                return template
        raise NotFound()

    def retrieve(self, request, *args, **kwargs):
        return Response(PromptTemplateDetailSerializer(self.get_object()).data)
