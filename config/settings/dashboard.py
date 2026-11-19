"""Dashboard surface settings overlay (isolated host-only __Host- cookies)."""

import os

_ENV = os.environ.get("DJET_ENV", "dev").lower()
if _ENV == "prod":
    from .prod import *  # noqa: F403
elif _ENV == "test":
    from .test import *  # noqa: F403
else:
    from .dev import *  # noqa: F403

from .env import get_env  # noqa: E402

DJET_SURFACE = "dashboard"
ROOT_URLCONF = "config.urls_dashboard"

# Host-only __Host- cookie prevents subdomain cookie tossing from shop.<domain>
SESSION_COOKIE_NAME = "__Host-djet_admin_sid"
SESSION_COOKIE_DOMAIN = None
SESSION_COOKIE_PATH = "/"
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"

CSRF_USE_SESSIONS = True
CSRF_COOKIE_SECURE = True

_ADMIN_DOMAIN = get_env("ADMIN_DOMAIN", "admin.djet.localhost")
CSRF_TRUSTED_ORIGINS = [f"https://{_ADMIN_DOMAIN}"]
