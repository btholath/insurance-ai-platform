from django.apps import AppConfig


class ClaimsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.claims"
    label = "claims"

    def ready(self):
        from django.db.models.signals import post_save

        from apps.risk.signals import on_claim_saved

        post_save.connect(on_claim_saved, sender=self.get_model("Claim"))
