"""AppConfig for apps.payments."""

from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    """Payments configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payments"
