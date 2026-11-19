"""RFC 6238 TOTP, recovery codes, and mandatory 2FA enforcement tests."""

from __future__ import annotations

import time
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.models import AuditLog, Role, StaffUser
from apps.core.rbac import sync_builtin_roles
from apps.core.totp import (
    generate_provisioning_uri,
    generate_recovery_codes,
    generate_totp_secret,
    generate_totp_token,
    verify_totp_token,
)


@pytest.fixture(autouse=True)
def setup_roles_and_urls(db: None, settings: Any) -> None:
    settings.ROOT_URLCONF = "config.urls_dashboard"
    sync_builtin_roles()


def test_totp_token_generation_and_skew_verification() -> None:
    """TOTP generation produces 6-digit tokens and allows +-1 step clock drift."""
    secret = generate_totp_secret()
    assert len(secret) == 32

    now = int(time.time())
    current_token = generate_totp_token(secret, timestamp=now)
    assert len(current_token) == 6
    assert current_token.isdigit()

    # Current token verifies
    assert verify_totp_token(secret, current_token, current_timestamp=now) is True

    # Skew window: T - 30 seconds verifies
    past_token = generate_totp_token(secret, timestamp=now - 30)
    assert verify_totp_token(secret, past_token, current_timestamp=now) is True

    # Skew window: T + 30 seconds verifies
    future_token = generate_totp_token(secret, timestamp=now + 30)
    assert verify_totp_token(secret, future_token, current_timestamp=now) is True

    # Outside skew window: T - 90 seconds fails
    too_old_token = generate_totp_token(secret, timestamp=now - 90)
    assert verify_totp_token(secret, too_old_token, current_timestamp=now) is False


def test_recovery_codes_generation_format() -> None:
    """generate_recovery_codes produces 10 uppercase alphanumeric codes."""
    codes = generate_recovery_codes(count=10)
    assert len(codes) == 10
    for code in codes:
        assert len(code) == 9  # XXXX-XXXX
        assert "-" in code
        assert code == code.upper()


def test_provisioning_uri_format() -> None:
    """Provisioning URI creates valid otpauth URL with issuer and account name."""
    secret = "JBSWY3DPEHPK3PXP"
    uri = generate_provisioning_uri(secret, "admin@djet.store", issuer="DJET Store")
    assert uri.startswith("otpauth://totp/DJET%20Store:admin@djet.store?")
    assert f"secret={secret}" in uri
    assert "issuer=DJET+Store" in uri or "issuer=DJET%20Store" in uri


@pytest.mark.django_db
def test_mandatory_2fa_enforcement_for_owner_and_manager() -> None:
    """Owner and Manager roles require 2FA; un-enrolled users are redirected to setup."""
    owner_role = Role.objects.get(name="Owner")
    manager_role = Role.objects.get(name="Manager")
    cashier_role = Role.objects.get(name="Cashier")

    owner = StaffUser.objects.create_user(
        username="unprotected_owner",
        email="owner@example.com",
        password="ValidPassword123!",
        role=owner_role,
        is_staff=True,
        totp_enabled=False,
    )
    manager = StaffUser.objects.create_user(
        username="unprotected_manager",
        email="manager@example.com",
        password="ValidPassword123!",
        role=manager_role,
        is_staff=True,
        totp_enabled=False,
    )
    cashier = StaffUser.objects.create_user(
        username="normal_cashier",
        email="cashier@example.com",
        password="ValidPassword123!",
        role=cashier_role,
        is_staff=True,
        totp_enabled=False,
    )

    assert owner.requires_2fa_enforcement() is True
    assert manager.requires_2fa_enforcement() is True
    assert cashier.requires_2fa_enforcement() is False

    # Owner attempts to access operational today page
    client = Client()
    client.force_login(owner)
    resp = client.get(reverse("dashboard-today"))
    assert resp.status_code == 302
    assert getattr(resp, "url", "") == reverse("dashboard-2fa-setup")

    # Cashier (optional 2FA) is NOT redirected
    cashier_client = Client()
    cashier_client.force_login(cashier)
    cashier_resp = cashier_client.get(reverse("dashboard-today"))
    assert cashier_resp.status_code == 200


@pytest.mark.django_db
def test_2fa_login_challenge_with_totp_and_recovery_codes() -> None:
    """User with 2FA enabled goes through challenge; accepts TOTP or recovery code."""
    role = Role.objects.get(name="Cashier")
    secret = generate_totp_secret()
    recovery_code = "ABCD-1234"

    user = StaffUser.objects.create_user(
        username="secured_cashier",
        email="secured@example.com",
        password="SecurePassword123!",
        role=role,
        is_staff=True,
        totp_enabled=True,
        totp_secret=secret,
        recovery_codes=[recovery_code],
    )

    client = Client()
    login_resp = client.post(
        reverse("dashboard-login"),
        {"username": "secured_cashier", "password": "SecurePassword123!"},
    )
    assert login_resp.status_code == 302
    assert getattr(login_resp, "url", "") == reverse("dashboard-2fa-verify")

    # 1. Invalid code rejected
    verify_fail = client.post(
        reverse("dashboard-2fa-verify"),
        {"code": "999999"},
    )
    assert verify_fail.status_code == 200
    assert "Invalid authentication code" in verify_fail.content.decode()

    # 2. Single-use recovery code accepted and consumed
    verify_rec = client.post(
        reverse("dashboard-2fa-verify"),
        {"code": "ABCD-1234"},
    )
    assert verify_rec.status_code == 302
    assert getattr(verify_rec, "url", "") == reverse("dashboard-today")

    user.refresh_from_db()
    assert "ABCD-1234" not in user.recovery_codes  # Consumed!

    audit = AuditLog.objects.filter(action="auth:recovery_code_used", actor=user).first()
    assert audit is not None
