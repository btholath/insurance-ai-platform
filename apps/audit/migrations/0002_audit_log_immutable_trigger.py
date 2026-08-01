from django.db import migrations

CREATE_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION audit_log_immutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_auditlog records are append-only and cannot be updated or deleted';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_immutable
    BEFORE UPDATE OR DELETE ON audit_auditlog
    FOR EACH ROW EXECUTE FUNCTION audit_log_immutable();
"""

DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS audit_log_immutable ON audit_auditlog;
DROP FUNCTION IF EXISTS audit_log_immutable();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_TRIGGER_SQL, reverse_sql=DROP_TRIGGER_SQL),
    ]
