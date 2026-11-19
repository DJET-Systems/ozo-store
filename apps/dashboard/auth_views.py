"""Staff authentication, 2FA (TOTP) enrollment/verification, lockout, and invitations."""

from __future__ import annotations

import hashlib
from datetime import timedelta

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.core.models import AuditLog, StaffInvite, StaffUser
from apps.core.totp import (
    generate_provisioning_uri,
    generate_recovery_codes,
    generate_totp_secret,
    verify_totp_token,
)


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    """Staff dashboard login with Argon2id, lockout protection, and 2FA challenge."""
    if request.user.is_authenticated and getattr(request.user, "is_staff", False):
        return redirect("dashboard-today")

    error_message: str | None = None
    next_url = request.GET.get("next") or request.POST.get("next") or reverse("dashboard-today")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = StaffUser.objects.filter(username=username).first()

        # Check account lockout
        if user and user.is_locked():
            remaining_mins = int((user.locked_until - timezone.now()).total_seconds() // 60) + 1  # type: ignore[operator]
            error_message = (
                f"Account is temporarily locked due to excessive failed attempts. "
                f"Please try again in {remaining_mins} minute(s)."
            )
            AuditLog.log_action(
                action="auth:lockout_attempt",
                entity_type="StaffUser",
                entity_id=str(user.id),
                actor=user,
                ip_address=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        else:
            authenticated_user = authenticate(request, username=username, password=password)

            if authenticated_user and getattr(authenticated_user, "is_staff", False):
                staff_user: StaffUser = authenticated_user
                # Reset failed attempts
                staff_user.failed_login_attempts = 0
                staff_user.locked_until = None
                staff_user.save(update_fields=["failed_login_attempts", "locked_until"])

                # Check if 2FA verification is required
                if staff_user.totp_enabled:
                    request.session["pre_2fa_user_id"] = staff_user.id
                    request.session["pre_2fa_next_url"] = next_url
                    return redirect("dashboard-2fa-verify")

                # If 2FA is mandatory for this role but not yet enabled, redirect to setup
                if staff_user.requires_2fa_enforcement():
                    login(request, staff_user)
                    request.session.cycle_key()
                    AuditLog.log_action(
                        action="auth:login_requires_2fa",
                        entity_type="StaffUser",
                        entity_id=str(staff_user.id),
                        actor=staff_user,
                        ip_address=request.META.get("REMOTE_ADDR"),
                    )
                    return redirect("dashboard-2fa-setup")

                # Standard login
                login(request, staff_user)
                request.session.cycle_key()
                AuditLog.log_action(
                    action="auth:login_success",
                    entity_type="StaffUser",
                    entity_id=str(staff_user.id),
                    actor=staff_user,
                    ip_address=request.META.get("REMOTE_ADDR"),
                )
                return redirect(next_url)

            # Failed authentication
            if user:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= 5:
                    user.locked_until = timezone.now() + timedelta(minutes=15)
                    AuditLog.log_action(
                        action="auth:account_locked",
                        entity_type="StaffUser",
                        entity_id=str(user.id),
                        actor=user,
                        ip_address=request.META.get("REMOTE_ADDR"),
                        diff={"failed_attempts": user.failed_login_attempts},
                    )
                user.save(update_fields=["failed_login_attempts", "locked_until"])

            error_message = "Invalid staff credentials."

    return render(
        request,
        "dashboard/login.html",
        {"error_message": error_message, "next_url": next_url},
    )


@require_http_methods(["POST", "GET"])
def logout_view(request: HttpRequest) -> HttpResponse:
    """Log out staff member and rotate session key."""
    if request.user.is_authenticated:
        AuditLog.log_action(
            action="auth:logout",
            entity_type="StaffUser",
            entity_id=str(request.user.id),
            actor=request.user,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
    logout(request)
    request.session.cycle_key()
    return redirect("dashboard-login")


@require_http_methods(["GET", "POST"])
def two_factor_verify_view(request: HttpRequest) -> HttpResponse:
    """Verify 6-digit TOTP code or single-use recovery code during login challenge."""
    user_id = request.session.get("pre_2fa_user_id")
    if not user_id:
        return redirect("dashboard-login")

    user = StaffUser.objects.filter(id=user_id, is_active=True).first()
    if not user:
        return redirect("dashboard-login")

    error_message: str | None = None
    next_url = request.session.get("pre_2fa_next_url") or reverse("dashboard-today")

    if request.method == "POST":
        code = request.POST.get("code", "").strip().upper()

        # 1. Try TOTP token verification
        is_valid_totp = verify_totp_token(user.totp_secret, code)

        # 2. Try single-use recovery code verification
        is_recovery_code = False
        if not is_valid_totp and user.recovery_codes:
            clean_code = code.replace(" ", "")
            if clean_code in user.recovery_codes:
                is_recovery_code = True
                user.recovery_codes.remove(clean_code)
                user.save(update_fields=["recovery_codes"])
                AuditLog.log_action(
                    action="auth:recovery_code_used",
                    entity_type="StaffUser",
                    entity_id=str(user.id),
                    actor=user,
                    ip_address=request.META.get("REMOTE_ADDR"),
                    diff={"remaining_recovery_codes": len(user.recovery_codes)},
                )

        if is_valid_totp or is_recovery_code:
            # Successfully authenticated with 2FA
            del request.session["pre_2fa_user_id"]
            if "pre_2fa_next_url" in request.session:
                del request.session["pre_2fa_next_url"]

            login(request, user)
            request.session.cycle_key()
            AuditLog.log_action(
                action="auth:2fa_success",
                entity_type="StaffUser",
                entity_id=str(user.id),
                actor=user,
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            return redirect(next_url)

        error_message = "Invalid authentication code or recovery code."

    return render(
        request,
        "dashboard/two_factor_verify.html",
        {"error_message": error_message, "username": user.username},
    )


@require_http_methods(["GET", "POST"])
def two_factor_setup_view(request: HttpRequest) -> HttpResponse:
    """Enroll staff account in Two-Factor Authentication (TOTP)."""
    if not request.user.is_authenticated or not getattr(request.user, "is_staff", False):
        return redirect("dashboard-login")

    user: StaffUser = request.user
    error_message: str | None = None
    success_codes: list[str] | None = None

    # Retrieve or generate secret in session
    session_secret = request.session.get("pending_totp_secret")
    session_codes = request.session.get("pending_recovery_codes")

    if not session_secret or not session_codes:
        session_secret = generate_totp_secret()
        session_codes = generate_recovery_codes()
        request.session["pending_totp_secret"] = session_secret
        request.session["pending_recovery_codes"] = session_codes

    provisioning_uri = generate_provisioning_uri(session_secret, user.username, issuer="DJET Store")

    if request.method == "POST":
        token = request.POST.get("token", "").strip()
        if verify_totp_token(session_secret, token):
            user.totp_secret = session_secret
            user.totp_enabled = True
            user.recovery_codes = session_codes
            user.save(update_fields=["totp_secret", "totp_enabled", "recovery_codes"])

            del request.session["pending_totp_secret"]
            del request.session["pending_recovery_codes"]

            AuditLog.log_action(
                action="auth:2fa_enrolled",
                entity_type="StaffUser",
                entity_id=str(user.id),
                actor=user,
                ip_address=request.META.get("REMOTE_ADDR"),
            )
            success_codes = session_codes
        else:
            error_message = "Invalid confirmation token. Please check your authenticator clock."

    return render(
        request,
        "dashboard/two_factor_setup.html",
        {
            "secret": session_secret,
            "provisioning_uri": provisioning_uri,
            "error_message": error_message,
            "success_codes": success_codes,
            "recovery_codes": session_codes,
            "is_enforced": user.requires_2fa_enforcement(),
        },
    )


@require_http_methods(["GET", "POST"])
def invite_accept_view(request: HttpRequest, token: str) -> HttpResponse:
    """Accept single-use invitation link and configure initial account password."""
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    invite = StaffInvite.objects.filter(token_hash=token_hash).first()

    if not invite or not invite.is_valid():
        return render(
            request,
            "dashboard/invite_invalid.html",
            {"message": "Invitation token is invalid or has expired."},
        )

    error_message: str | None = None

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not username:
            error_message = "Username is required."
        elif password != confirm_password:
            error_message = "Passwords do not match."
        elif len(password) < 12:
            error_message = "Password must be at least 12 characters long."
        elif StaffUser.objects.filter(username=username).exists():
            error_message = "Username is already taken."
        else:
            try:
                validate_password(password)
                new_staff = StaffUser.objects.create_user(
                    username=username,
                    email=invite.email,
                    password=password,
                    role=invite.role,
                    is_staff=True,
                )
                invite.accepted_at = timezone.now()
                invite.save(update_fields=["accepted_at"])

                AuditLog.log_action(
                    action="staff:invite_accepted",
                    entity_type="StaffUser",
                    entity_id=str(new_staff.id),
                    actor=new_staff,
                    diff={"role": invite.role.name, "email": invite.email},
                    ip_address=request.META.get("REMOTE_ADDR"),
                )

                login(request, new_staff)
                request.session.cycle_key()

                if new_staff.requires_2fa_enforcement():
                    return redirect("dashboard-2fa-setup")
                return redirect("dashboard-today")
            except ValidationError as e:
                error_message = "; ".join(e.messages)

    return render(
        request,
        "dashboard/invite_accept.html",
        {"invite": invite, "error_message": error_message},
    )
