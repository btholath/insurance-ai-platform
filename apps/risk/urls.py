"""
Risk API routes, mounted at /api/risk/ (T038).

The top-level prefix is load-bearing, not cosmetic. The spec's illustrative
path was /api/customers/{id}/risk-assessment/, which falls under the
"/api/customers/" prefix already registered in apps.core.audit_routes --
match() would return the CUSTOMER entry, so every risk refusal would be
audited as `customer.viewed` against `customers.Customer`, consulting
Customer's seven view roles instead of Risk's five. Customer Service is in
that set and not in Risk's, so a refused Customer Service request would be
classified an ordinary miss and never recorded at all.

Verified before the design was fixed; see specs/005-risk-scoring-engine/
research.md §1. Do not "simplify" this into a nested route.
"""
from rest_framework.routers import DefaultRouter

from .views import RiskAssessmentViewSet

router = DefaultRouter()
router.register("assessments", RiskAssessmentViewSet, basename="riskassessment")

urlpatterns = router.urls
