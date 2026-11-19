"""AppConfig for apps.shipping."""

from django.apps import AppConfig


class ShippingConfig(AppConfig):
    """Shipping configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.shipping"
