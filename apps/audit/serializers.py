from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id",
            "timestamp",
            "actor",
            "actor_identifier",
            "actor_role",
            "action",
            "target_type",
            "target_id",
            "outcome",
            "before",
            "after",
        ]
        read_only_fields = fields
