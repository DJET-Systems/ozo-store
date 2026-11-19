"""Time-Based One-Time Password (TOTP, RFC 6238) and recovery codes implementation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse


def generate_totp_secret() -> str:
    """Generate a high-entropy 160-bit (20 bytes) Base32-encoded TOTP secret."""
    raw_bytes = secrets.token_bytes(20)
    return base64.b32encode(raw_bytes).decode("ascii")


def get_totp_token(
    secret_b32: str,
    *,
    for_time: float | None = None,
    timestamp: float | None = None,
    time_step: int = 30,
) -> str:
    """Compute the 6-digit TOTP token for a given Base32 secret at the specified timestamp."""
    effective_time = for_time if for_time is not None else timestamp
    curr_time = time.time() if effective_time is None else effective_time
    counter = int(curr_time // time_step)
    counter_bytes = struct.pack(">Q", counter)

    # Clean secret formatting (strip whitespace/padding if present)
    clean_secret = secret_b32.strip().upper().replace(" ", "")
    # Add base32 padding if needed
    missing_padding = len(clean_secret) % 8
    if missing_padding:
        clean_secret += "=" * (8 - missing_padding)

    secret_bytes = base64.b32decode(clean_secret)
    h = hmac.new(secret_bytes, counter_bytes, hashlib.sha1).digest()

    # Dynamic truncation
    offset = h[-1] & 0x0F
    binary_val = (
        ((h[offset] & 0x7F) << 24)
        | ((h[offset + 1] & 0xFF) << 16)
        | ((h[offset + 2] & 0xFF) << 8)
        | (h[offset + 3] & 0xFF)
    )
    token = binary_val % 1_000_000
    return f"{token:06d}"


# Alias for explicit clarity
generate_totp_token = get_totp_token


def verify_totp_token(
    secret_b32: str,
    token: str,
    *,
    window: int = 1,
    time_step: int = 30,
    current_timestamp: float | None = None,
) -> bool:
    """Verify a TOTP token against a Base32 secret allowing clock drift within window."""
    if not token or len(token.strip()) != 6 or not token.strip().isdigit():
        return False

    clean_token = token.strip()
    now = time.time() if current_timestamp is None else current_timestamp

    for offset in range(-window, window + 1):
        candidate_time = now + (offset * time_step)
        expected = get_totp_token(secret_b32, for_time=candidate_time, time_step=time_step)
        if secrets.compare_digest(expected, clean_token):
            return True

    return False


def generate_recovery_codes(count: int = 8) -> list[str]:
    """Generate cryptographically secure single-use recovery codes in XXXX-XXXX format."""
    codes: list[str] = []
    for _ in range(count):
        hex_str = secrets.token_hex(4).upper()
        codes.append(f"{hex_str[:4]}-{hex_str[4:]}")
    return codes


def generate_provisioning_uri(
    secret_b32: str,
    username: str,
    *,
    issuer: str = "DJET Store",
) -> str:
    """Generate standard otpauth:// URL for authenticator app enrollment."""
    label = f"{issuer}:{username}"
    params = {
        "secret": secret_b32.strip().upper(),
        "issuer": issuer,
        "algorithm": "SHA1",
        "digits": "6",
        "period": "30",
    }
    return f"otpauth://totp/{urllib.parse.quote(label, safe=':@')}?{urllib.parse.urlencode(params)}"
