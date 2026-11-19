"""AppConfig for apps.catalog."""

from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """Catalog configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
