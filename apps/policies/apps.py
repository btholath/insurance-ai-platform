from django.apps import AppConfig


class PoliciesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.policies"
    label = "policies"

    def ready(self):
        from django.db.models.signals import post_save

        from apps.risk.signals import on_policy_saved

        post_save.connect(on_policy_saved, sender=self.get_model("Policy"))
