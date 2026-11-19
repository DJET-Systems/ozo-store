"""Add PostgreSQL immutable append-only trigger to inventory_stock_movement."""

from django.db import migrations


TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION fn_prevent_stock_movement_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Table inventory_stock_movement is append-only: UPDATE and DELETE operations are forbidden.'
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_stock_movement_update_delete ON inventory_stock_movement;

CREATE TRIGGER trg_prevent_stock_movement_update_delete
BEFORE UPDATE OR DELETE ON inventory_stock_movement
FOR EACH ROW EXECUTE FUNCTION fn_prevent_stock_movement_modification();
"""

REVERSE_SQL = """
DROP TRIGGER IF EXISTS trg_prevent_stock_movement_update_delete ON inventory_stock_movement;
DROP FUNCTION IF EXISTS fn_prevent_stock_movement_modification();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=TRIGGER_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]
