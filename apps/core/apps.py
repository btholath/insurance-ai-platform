from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"

    def ready(self):
        # Populated here rather than at module import: the exception
        # handler is named in settings, so this module is reachable before
        # the app registry is ready to import models.
        from apps.core import audit_routes

        audit_routes.register_defaults()
