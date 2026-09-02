"""
Prompt library routes, mounted at /api/prompts/ (T047).

The top-level prefix is load-bearing, not cosmetic -- the same lesson
apps/risk/urls.py records. A path nested under an existing registry prefix is
swallowed by that entry: apps.core.audit_routes.match() returns the longest
matching prefix, so every prompt refusal would be audited under the wrong
module's action name, target type, and role set.

There is no plausible parent here in any case -- a prompt template belongs to
no customer, policy or claim. Do not "tidy" this into a nested route.
"""
from rest_framework.routers import DefaultRouter

from .views import PromptTemplateViewSet

router = DefaultRouter()
router.register("templates", PromptTemplateViewSet, basename="prompttemplate")

urlpatterns = router.urls
