from django.apps import AppConfig


class CustomersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.customers"
    label = "customers"

    def ready(self):
        from django.db.models.signals import post_save

        from apps.risk.signals import on_customer_saved

        post_save.connect(on_customer_saved, sender=self.get_model("Customer"))
