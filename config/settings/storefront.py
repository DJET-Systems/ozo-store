"""Storefront surface settings overlay."""

import os

_ENV = os.environ.get("DJET_ENV", "dev").lower()
if _ENV == "prod":
    from .prod import *  # noqa: F403
elif _ENV == "test":
    from .test import *  # noqa: F403
else:
    from .dev import *  # noqa: F403

from .env import get_env  # noqa: E402

DJET_SURFACE = "storefront"
ROOT_URLCONF = "config.urls_storefront"

SESSION_COOKIE_NAME = "djet_store_sid"
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_DOMAIN = None
SESSION_COOKIE_PATH = "/"

CSRF_COOKIE_NAME = "djet_store_csrf"
CSRF_COOKIE_SAMESITE = "Lax"

_STORE_DOMAIN = get_env("STORE_DOMAIN", "shop.djet.localhost")
CSRF_TRUSTED_ORIGINS = [f"https://{_STORE_DOMAIN}"]
if _ENV != "prod":
    CSRF_TRUSTED_ORIGINS.append(f"http://{_STORE_DOMAIN}")
