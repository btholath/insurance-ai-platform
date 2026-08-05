from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .checks import check_cache, check_database


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        database_status = check_database()
        cache_status = check_cache()

        healthy = database_status == "ok" and cache_status == "ok"

        body = {
            "status": "healthy" if healthy else "unhealthy",
            "checks": {
                "database": {"status": database_status},
                "cache": {"status": cache_status},
            },
        }
        http_status = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE

        return Response(body, status=http_status)
