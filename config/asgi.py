"""ASGI config for DJET Store."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.storefront")
application = get_asgi_application()
