"""AppConfig for apps.customers."""

from django.apps import AppConfig


class CustomersConfig(AppConfig):
    """Customers configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.customers"
