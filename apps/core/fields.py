"""Custom encrypted model fields for sensitive credentials at rest."""

from __future__ import annotations

import base64
import hashlib
from typing import TYPE_CHECKING, Any

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models


def _get_fernet() -> Fernet:
    """Derive a deterministic 32-byte Fernet key from Django SECRET_KEY or FIELD_ENCRYPTION_KEY."""
    raw_key = getattr(settings, "FIELD_ENCRYPTION_KEY", None) or settings.SECRET_KEY
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    url_safe_key = base64.urlsafe_b64encode(digest)
    return Fernet(url_safe_key)


if TYPE_CHECKING:
    _CharFieldBase = models.CharField[Any, Any]
else:
    _CharFieldBase = models.CharField


class EncryptedCharField(_CharFieldBase):
    """CharField that transparently encrypts values at rest using AES-CBC/HMAC (Fernet)."""

    def get_prep_value(self, value: Any) -> Any:
        prep = super().get_prep_value(value)
        if prep is None or prep == "":
            return prep
        fernet = _get_fernet()
        encrypted = fernet.encrypt(str(prep).encode("utf-8"))
        return encrypted.decode("ascii")

    def from_db_value(self, value: Any, expression: Any, connection: Any) -> str | None:
        if value is None:
            return None
        if value == "":
            return ""
        try:
            fernet = _get_fernet()
            decrypted = fernet.decrypt(str(value).encode("ascii"))
            return decrypted.decode("utf-8")
        except Exception:
            # If decryption fails (e.g. unencrypted legacy value), return raw value
            return str(value)

    def to_python(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        val = super().to_python(value)
        return str(val) if val is not None else None
