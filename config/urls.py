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
    # Top-level prefix, NOT nested under /api/customers/. The nested path
    # would fall under the customers entry in apps.core.audit_routes, so
    # every risk refusal would be audited as a customer refusal against the
    # wrong role set. See specs/005-risk-scoring-engine/research.md §1.
    path("api/risk/", include("apps.risk.urls")),
]
