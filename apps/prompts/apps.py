from django.apps import AppConfig


class PromptsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.prompts"
    label = "prompts"

    def ready(self):
        """
        Validate the whole library at startup (FR-008).

        Validating here rather than at import time is what makes "fail loudly
        and completely" concrete: a template whose declaration disagrees with
        its body stops the process from starting, which is the loudest
        failure available. A database-resident library could only be checked
        at write time, leaving a window where the code on disk is valid and
        the stored library is not.

        The import is lazy, inside the function, for the reason
        `apps/core/apps.py` records: at module-import time the app registry is
        not yet populated, and validation resolves real models.

        The module's audited-route entry is NOT registered here -- it lives in
        `apps.core.audit_routes.register_defaults()` alongside the other four,
        so all five consumers are readable in one place and a reviewer can
        compare the role sets side by side.
        """
        from . import library, validation

        validation.validate_library(library.TEMPLATES)
