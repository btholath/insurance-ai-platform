from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.permissions import HasRole


class PlaceholderView(APIView):
    permission_classes = [HasRole(Role.UNDERWRITER, Role.PRODUCT_MANAGER, Role.SYSTEM_ADMINISTRATOR)]

    def get(self, request):
        return Response({"module": "policies", "status": "placeholder"})
