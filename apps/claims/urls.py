from rest_framework.routers import DefaultRouter

from .views import ClaimLoadAnomalyViewSet, ClaimViewSet

# The anomalies route is registered FIRST. DefaultRouter matches in
# registration order, and the claim detail pattern (r"^(?P<pk>[^/.]+)/$")
# would otherwise swallow "anomalies/" as a claim id.
router = DefaultRouter()
router.register("anomalies", ClaimLoadAnomalyViewSet, basename="claim-anomaly")
router.register("", ClaimViewSet, basename="claim")

urlpatterns = router.urls
