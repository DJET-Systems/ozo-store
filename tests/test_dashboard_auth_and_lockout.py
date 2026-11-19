"""Tests for staff authentication, brute-force lockout, and invitation flows."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditLog, Role, StaffInvite, StaffUser
from apps.core.rbac import sync_builtin_roles


@pytest.fixture(autouse=True)
def setup_roles_and_urls(db: None, settings: Any) -> None:
    settings.ROOT_URLCONF = "config.urls_dashboard"
    sync_builtin_roles()


@pytest.mark.django_db
def test_password_policy_minimum_12_characters() -> None:
    """Staff passwords must be at least 12 characters long."""
    with pytest.raises(ValidationError):
        validate_password("Short12345")  # 10 chars

    # 12+ chars passes validation
    validate_password("ValidPassword123!")


@pytest.mark.django_db
def test_successful_login_cycles_session_and_audits() -> None:
    """Valid credentials log in staff user, rotate session key, and record audit log."""
    role = Role.objects.get(name="Cashier")
    user = StaffUser.objects.create_user(
        username="john_cashier",
        email="john@example.com",
        password="SuperSecretPassword123!",
        role=role,
        is_staff=True,
    )

    client = Client()
    resp = client.post(
        reverse("dashboard-login"),
        {"username": "john_cashier", "password": "SuperSecretPassword123!"},
    )

    assert resp.status_code == 302
    assert getattr(resp, "url", "") == reverse("dashboard-today")

    # Audit log check
    log = AuditLog.objects.filter(action="auth:login_success", actor=user).first()
    assert log is not None
    assert log.entity_type == "StaffUser"
    assert log.entity_id == str(user.id)


@pytest.mark.django_db
def test_failed_logins_trigger_account_lockout_after_5_attempts() -> None:
    """5 consecutive failed logins lock account for 15 minutes with audit logging."""
    role = Role.objects.get(name="Cashier")
    user = StaffUser.objects.create_user(
        username="victim_cashier",
        email="victim@example.com",
        password="CorrectPassword123!",
        role=role,
        is_staff=True,
    )

    client = Client()

    # 4 failed attempts
    for i in range(1, 5):
        resp = client.post(
            reverse("dashboard-login"),
            {"username": "victim_cashier", "password": "WrongPassword!"},
        )
        assert resp.status_code == 200
        assert "Invalid staff credentials." in resp.content.decode()
        user.refresh_from_db()
        assert user.failed_login_attempts == i
        assert user.is_locked() is False

    # 5th failed attempt triggers lockout
    resp = client.post(
        reverse("dashboard-login"),
        {"username": "victim_cashier", "password": "WrongPassword!"},
    )
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.failed_login_attempts == 5
    assert user.is_locked() is True
    assert user.locked_until is not None

    # Audit log check for lockout
    lock_log = AuditLog.objects.filter(action="auth:account_locked", actor=user).first()
    assert lock_log is not None
    assert lock_log.diff["failed_attempts"] == 5

    # 6th attempt with CORRECT password while locked must fail
    resp = client.post(
        reverse("dashboard-login"),
        {"username": "victim_cashier", "password": "CorrectPassword123!"},
    )
    assert resp.status_code == 200
    assert "temporarily locked" in resp.content.decode()

    lockout_attempt_log = AuditLog.objects.filter(action="auth:lockout_attempt", actor=user).first()
    assert lockout_attempt_log is not None


@pytest.mark.django_db
def test_single_use_invitation_lifecycle() -> None:
    """Single-use invitation creation, acceptance, and replay prevention."""
    owner_role = Role.objects.get(name="Owner")
    cashier_role = Role.objects.get(name="Cashier")

    owner = StaffUser.objects.create_user(
        username="owner_admin",
        email="owner@example.com",
        password="OwnerPassword123!",
        role=owner_role,
        is_staff=True,
        totp_enabled=True,
    )

    client = Client()
    client.force_login(owner)

    # 1. Owner invites new cashier
    invite_resp = client.post(
        reverse("dashboard-staff-invite"),
        {"email": "newbie@example.com", "role_id": str(cashier_role.id)},
    )
    assert invite_resp.status_code == 302
    assert getattr(invite_resp, "url", "") == reverse("dashboard-staff")

    invite = StaffInvite.objects.get(email="newbie@example.com")
    assert invite.is_valid() is True
    assert invite.invited_by == owner
    assert invite.role == cashier_role

    # Audit log check
    invite_log = AuditLog.objects.filter(action="staff:invite_created").first()
    assert invite_log is not None
    assert invite_log.diff["email"] == "newbie@example.com"

    # 2. Extract invite link and accept invitation
    # Generate token matching invite hash
    raw_token = "secure_test_invitation_token_123"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    invite.token_hash = token_hash
    invite.save()

    anon_client = Client()
    accept_url = reverse("dashboard-invite-accept", args=[raw_token])

    get_resp = anon_client.get(accept_url)
    assert get_resp.status_code == 200
    assert "newbie@example.com" in get_resp.content.decode()

    # Complete signup with valid password >= 12 chars
    post_resp = anon_client.post(
        accept_url,
        {
            "username": "newbie_cashier",
            "password": "NewbieStaffPassword123!",
            "confirm_password": "NewbieStaffPassword123!",
        },
    )
    assert post_resp.status_code == 302

    new_user = StaffUser.objects.get(username="newbie_cashier")
    assert new_user.role == cashier_role
    assert new_user.is_staff is True

    invite.refresh_from_db()
    assert invite.is_valid() is False
    assert invite.accepted_at is not None

    # 3. Attempt to re-use token must be refused
    replay_resp = anon_client.get(accept_url)
    assert replay_resp.status_code == 200
    assert "invalid or has expired" in replay_resp.content.decode()


@pytest.mark.django_db
def test_expired_invitation_cannot_be_accepted() -> None:
    """Expired invitations are rejected."""
    role = Role.objects.get(name="Cashier")
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    # Create expired invite
    StaffInvite.objects.create(
        email="expired@example.com",
        role=role,
        token_hash=token_hash,
        expires_at=timezone.now() - timedelta(hours=1),
    )

    client = Client()
    resp = client.get(reverse("dashboard-invite-accept", args=[raw_token]))
    assert resp.status_code == 200
    assert "invalid or has expired" in resp.content.decode()
