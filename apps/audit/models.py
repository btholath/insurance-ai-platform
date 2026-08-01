from django.conf import settings
from django.db import models


class AuditLogQuerySet(models.QuerySet):
    def update(self, *args, **kwargs):
        raise NotImplementedError("AuditLog records are append-only and cannot be updated.")

    def delete(self, *args, **kwargs):
        raise NotImplementedError("AuditLog records are append-only and cannot be deleted.")


class AuditLogManager(models.Manager.from_queryset(AuditLogQuerySet)):
    pass


class AuditLog(models.Model):
    class Outcome(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        REFUSED = "refused", "Refused"

    timestamp = models.DateTimeField(auto_now_add=True, editable=False, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    actor_identifier = models.CharField(max_length=254)
    actor_role = models.CharField(max_length=32, blank=True)
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64, db_index=True)
    target_id = models.CharField(max_length=64, db_index=True)
    outcome = models.CharField(max_length=16, choices=Outcome.choices)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    context = models.JSONField(null=True, blank=True)

    objects = AuditLogManager()

    class Meta:
        indexes = [
            models.Index(fields=["target_type", "target_id", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.action} on {self.target_type}:{self.target_id} at {self.timestamp}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise NotImplementedError("AuditLog records are append-only and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise NotImplementedError("AuditLog records are append-only and cannot be deleted.")
