"""Add PostgreSQL immutable append-only trigger to core_audit_log."""

from django.db import migrations


TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION fn_prevent_audit_log_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Table core_audit_log is append-only: UPDATE and DELETE operations are forbidden.'
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_audit_log_update_delete ON core_audit_log;

CREATE TRIGGER trg_prevent_audit_log_update_delete
BEFORE UPDATE OR DELETE ON core_audit_log
FOR EACH ROW EXECUTE FUNCTION fn_prevent_audit_log_modification();
"""

REVERSE_SQL = """
DROP TRIGGER IF EXISTS trg_prevent_audit_log_update_delete ON core_audit_log;
DROP FUNCTION IF EXISTS fn_prevent_audit_log_modification();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_featureflag_storesettings_auditlog"),
    ]

    operations = [
        migrations.RunSQL(
            sql=TRIGGER_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]
