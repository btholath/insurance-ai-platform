from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", include("apps.health.urls")),
    path("api/", include("apps.accounts.urls")),
    path("api/audit/", include("apps.audit.urls")),
    path("api/customers/", include("apps.customers.urls")),
    path("api/policies/", include("apps.policies.urls")),
    path("api/claims/", include("apps.claims.urls")),
]
