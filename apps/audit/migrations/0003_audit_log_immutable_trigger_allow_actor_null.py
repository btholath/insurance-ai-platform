from django.db import migrations

CREATE_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION audit_log_immutable() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        -- The one legitimate system-driven exception: User.actor's on_delete=SET_NULL
        -- issues an UPDATE that nulls actor_id and changes nothing else (FR-021).
        -- Any other column changing, or actor_id changing to anything but NULL,
        -- is still rejected.
        IF NEW.actor_id IS NULL
            AND NEW.timestamp IS NOT DISTINCT FROM OLD.timestamp
            AND NEW.actor_identifier IS NOT DISTINCT FROM OLD.actor_identifier
            AND NEW.actor_role IS NOT DISTINCT FROM OLD.actor_role
            AND NEW.action IS NOT DISTINCT FROM OLD.action
            AND NEW.target_type IS NOT DISTINCT FROM OLD.target_type
            AND NEW.target_id IS NOT DISTINCT FROM OLD.target_id
            AND NEW.outcome IS NOT DISTINCT FROM OLD.outcome
            AND NEW.before IS NOT DISTINCT FROM OLD.before
            AND NEW.after IS NOT DISTINCT FROM OLD.after
            AND NEW.context IS NOT DISTINCT FROM OLD.context
        THEN
            RETURN NEW;
        END IF;
    END IF;

    RAISE EXCEPTION 'audit_auditlog records are append-only and cannot be updated or deleted';
END;
$$ LANGUAGE plpgsql;
"""

REVERT_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION audit_log_immutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_auditlog records are append-only and cannot be updated or deleted';
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0002_audit_log_immutable_trigger"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_TRIGGER_SQL, reverse_sql=REVERT_TRIGGER_SQL),
    ]
