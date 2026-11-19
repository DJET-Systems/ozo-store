"""Core staff user, RBAC roles, invites, audit log, and store settings."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar, cast

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from apps.core.fields import EncryptedCharField


class TimeStampedModel(models.Model):
    """Abstract base model adding created_at and updated_at timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Role(TimeStampedModel):
    """Bundle of explicit permissions assignable to staff members."""

    name = models.CharField(max_length=64, unique=True)
    description = models.TextField(blank=True)
    permissions = models.JSONField(default=list, help_text="List of permission strings or ['*']")
    is_builtin = models.BooleanField(
        default=False, help_text="True if this role was generated from system defaults"
    )
    modified_by_merchant = models.BooleanField(
        default=False, help_text="True if merchant customized permissions, preventing auto-override"
    )

    class Meta:
        db_table = "core_role"
        verbose_name = "Role"
        verbose_name_plural = "Roles"
        ordering: ClassVar[tuple[str, ...]] = ("name",)

    def __str__(self) -> str:
        return self.name

    def has_permission(self, perm: str) -> bool:
        if "*" in self.permissions:
            return True
        return perm in self.permissions


class StaffUser(AbstractUser):
    """Merchant staff and operator account (distinct from storefront shoppers)."""

    role = models.ForeignKey(
        Role,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="staff_users",
    )
    totp_secret = EncryptedCharField(
        max_length=512, blank=True, default="", help_text="Encrypted Base32 TOTP secret"
    )
    totp_enabled = models.BooleanField(default=False)
    recovery_codes = models.JSONField(
        default=list, blank=True, help_text="List of single-use recovery codes"
    )
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "core_staff_user"
        verbose_name = "Staff user"
        verbose_name_plural = "Staff users"

    def has_perm(self, perm: str, obj: Any = None) -> bool:
        """Evaluate permission against superuser status and assigned RBAC role."""
        from apps.core.rbac import user_has_permission

        return user_has_permission(self, perm)

    def requires_2fa_enforcement(self) -> bool:
        """True if the user belongs to an executive role requiring mandatory 2FA enrollment."""
        if not self.is_active or not self.is_staff:
            return False
        return bool(self.role and self.role.name in {"Owner", "Manager"} and not self.totp_enabled)

    def is_locked(self) -> bool:
        """Check if account is temporarily locked due to brute-force rate limiting."""
        return bool(self.locked_until and self.locked_until > timezone.now())


class StaffInvite(TimeStampedModel):
    """Single-use invitation token for merchant onboarding or staff team invitations."""

    email = models.EmailField(db_index=True)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="invites")
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    created_by = models.ForeignKey(
        StaffUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_invites",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "core_staff_invite"
        verbose_name = "Staff invite"
        verbose_name_plural = "Staff invites"

    def __str__(self) -> str:
        return f"StaffInvite<{self.email} ({self.role.name})>"

    @property
    def invited_by(self) -> StaffUser | None:
        return self.created_by

    @invited_by.setter
    def invited_by(self, user: StaffUser | None) -> None:
        self.created_by = user

    def is_valid(self) -> bool:
        return self.accepted_at is None and self.expires_at > timezone.now()


class AuditLog(models.Model):
    """Immutable audit trail recording sensitive staff/system actions."""

    action = models.CharField(max_length=64, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    actor_email = models.EmailField(blank=True)
    entity_type = models.CharField(max_length=64, db_index=True)
    entity_id = models.CharField(max_length=64, db_index=True)
    diff_json = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    correlation_id = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "core_audit_log"
        ordering: ClassVar[tuple[str, ...]] = ("-created_at", "-id")
        verbose_name = "Audit log"
        verbose_name_plural = "Audit logs"

    def __str__(self) -> str:
        actor_name = self.actor_email or (self.actor.username if self.actor else "system")
        ts = f"{self.created_at:%Y-%m-%d %H:%M:%S}"
        return f"[{ts}] {actor_name} -> {self.action} on {self.entity_type}#{self.entity_id}"

    @property
    def diff(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.diff_json)

    @classmethod
    def log_action(
        cls,
        *,
        action: str,
        entity_type: str,
        entity_id: str | int,
        actor: Any = None,
        diff: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str = "",
        correlation_id: str = "",
    ) -> AuditLog:
        """Create an append-only audit log entry."""
        is_auth = bool(actor and hasattr(actor, "is_authenticated") and actor.is_authenticated)
        actor_user = actor if is_auth else None
        if isinstance(actor, str):
            actor_email = actor
        else:
            actor_email = getattr(actor, "email", "") if actor else ""
        return cls.objects.create(
            action=action,
            actor=actor_user,
            actor_email=actor_email,
            entity_type=entity_type,
            entity_id=str(entity_id),
            diff_json=diff or {},
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )


class StoreSettings(models.Model):
    """Singleton configuration for merchant runtime settings and active preset."""

    PRESET_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("general", "General Store"),
        ("electronics", "Electronics & Devices"),
        ("clothing", "Clothing Brand"),
        ("fashion", "Apparel & Footwear"),
        ("food", "Food & Restaurant"),
        ("minimarket", "Mini-Market"),
        ("groceries", "Supermarket & Groceries"),
    )

    TAX_MODE_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (
        ("none", "No Tax"),
        ("inclusive", "Tax Inclusive in Prices"),
        ("exclusive", "Tax Exclusive (Added at Checkout)"),
    )

    store_name_en = models.CharField(max_length=255, default="DJET Store")
    store_name_ar = models.CharField(max_length=255, default="متجر دجت")
    store_domain = models.CharField(max_length=255, default="shop.djet.localhost")
    default_currency = models.CharField(max_length=3, default="EGP")
    supported_currencies = models.JSONField(default=list, blank=True)
    primary_language = models.CharField(max_length=8, default="ar")
    supported_languages = models.JSONField(default=list, blank=True)
    active_preset = models.CharField(max_length=32, choices=PRESET_CHOICES, default="general")
    home_sections = models.JSONField(default=list, blank=True)
    brand_tokens = models.JSONField(default=dict, blank=True)
    whatsapp_number = models.CharField(max_length=32, blank=True)
    tax_mode = models.CharField(max_length=16, choices=TAX_MODE_CHOICES, default="none")
    default_tax_rate = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal("0.1400")
    )
    audit_retention_days = models.PositiveIntegerField(default=365)
    allow_negative_stock_global = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_store_settings"
        verbose_name = "Store settings"
        verbose_name_plural = "Store settings"

    def __str__(self) -> str:
        return f"{self.store_name_en} ({self.store_domain})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Enforce singleton pattern with fixed primary key id=1
        self.id = 1
        if not self.supported_currencies:
            self.supported_currencies = ["EGP"]
        if not self.supported_languages:
            self.supported_languages = ["ar", "en"]
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls) -> StoreSettings:
        """Retrieve the singleton StoreSettings instance, initializing with defaults if missing."""
        obj, _ = cls.objects.get_or_create(
            id=1,
            defaults={
                "store_name_en": "DJET Store",
                "store_name_ar": "متجر دجت",
                "supported_currencies": ["EGP"],
                "supported_languages": ["ar", "en"],
            },
        )
        return obj

    @classmethod
    def get_solo(cls) -> StoreSettings:
        """Alias for get_settings() providing singleton convenience."""
        return cls.get_settings()

    @property
    def preset(self) -> str:
        """Alias property for active_preset."""
        return self.active_preset

    @preset.setter
    def preset(self, value: str) -> None:
        self.active_preset = value


class FeatureFlag(TimeStampedModel):
    """Feature flag toggles for gradual rollout and add-on activation."""

    key = models.SlugField(max_length=64, unique=True)
    is_enabled = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "core_feature_flag"
        verbose_name = "Feature flag"
        verbose_name_plural = "Feature flags"

    def __str__(self) -> str:
        status = "ON" if self.is_enabled else "OFF"
        return f"{self.key} [{status}]"

    @classmethod
    def is_active(cls, key: str) -> bool:
        try:
            flag = cls.objects.get(key=key)
            return flag.is_enabled
        except cls.DoesNotExist:
            return False
