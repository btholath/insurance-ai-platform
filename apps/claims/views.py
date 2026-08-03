from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.permissions import HasRole


class PlaceholderView(APIView):
    permission_classes = [HasRole(Role.CLAIMS_ADJUSTER, Role.FRAUD_ANALYST, Role.SYSTEM_ADMINISTRATOR)]

    def get(self, request):
        return Response({"module": "claims", "status": "placeholder"})
