"""AppConfig for apps.purchasing."""

from django.apps import AppConfig


class PurchasingConfig(AppConfig):
    """Purchasing configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.purchasing"
