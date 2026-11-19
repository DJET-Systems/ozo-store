"""Tests for StoreSettings singleton, FeatureFlag toggles, and field encryption at rest."""

from django.db import connection

from apps.core.fields import EncryptedCharField
from apps.core.models import AuditLog, FeatureFlag, StaffUser, StoreSettings


def test_store_settings_singleton_enforcement(db):
    """Test that StoreSettings always enforces singleton ID=1."""
    s1 = StoreSettings.get_settings()
    assert s1.id == 1
    assert s1.default_currency == "EGP"
    assert "ar" in s1.supported_languages

    # Mutate and save
    s1.store_name_en = "Updated Store Name"
    s1.save()

    s2 = StoreSettings.get_settings()
    assert s2.id == 1
    assert s2.store_name_en == "Updated Store Name"

    # Attempting to save with a different ID still resets ID to 1
    s3 = StoreSettings(id=99, store_name_en="Forced ID")
    s3.save()
    assert s3.id == 1
    assert StoreSettings.objects.count() == 1


def test_feature_flag_evaluation(db):
    """Test FeatureFlag.is_active helper returns correct state."""
    assert not FeatureFlag.is_active("non_existent_feature")

    flag = FeatureFlag.objects.create(key="loyalty_points", is_enabled=False)
    assert not FeatureFlag.is_active("loyalty_points")

    flag.is_enabled = True
    flag.save()
    assert FeatureFlag.is_active("loyalty_points")
    assert "ON" in str(flag)


def test_audit_log_creation_and_string_representation(db):
    """Test AuditLog.log_action with both staff user and system actions."""
    # 1. System action without actor
    log_sys = AuditLog.log_action(
        action="system:backup",
        entity_type="System",
        entity_id="cron",
        diff={"status": "completed"},
    )
    assert log_sys.actor is None
    assert "system -> system:backup" in str(log_sys)

    # 2. Staff user action
    staff = StaffUser.objects.create_user(username="ahmed_ops", email="ahmed@example.com")
    log_staff = AuditLog.log_action(
        action="product:publish",
        entity_type="Product",
        entity_id="101",
        actor=staff,
        diff={"status": "active"},
        ip_address="192.168.1.100",
        correlation_id="corr-xyz-123",
    )
    assert log_staff.actor == staff
    assert log_staff.actor_email == "ahmed@example.com"
    assert log_staff.correlation_id == "corr-xyz-123"
    assert "ahmed@example.com -> product:publish" in str(log_staff)


def test_field_encryption_at_rest(db):
    """Test that EncryptedCharField encrypts data in raw SQL storage and decrypts transparently."""
    field = EncryptedCharField(max_length=255)
    secret_text = "paymob_live_sec_key_0123456789abcdef"

    # 1. Encryption
    encrypted_payload = field.get_prep_value(secret_text)
    assert encrypted_payload != secret_text
    assert secret_text not in encrypted_payload
    assert isinstance(encrypted_payload, str)

    # 2. Decryption
    decrypted_text = field.from_db_value(encrypted_payload, None, connection)
    assert decrypted_text == secret_text

    # 3. Handling None and empty strings
    assert field.get_prep_value(None) is None
    assert field.get_prep_value("") == ""
    assert field.from_db_value(None, None, connection) is None
    assert field.from_db_value("", None, connection) == ""
