"""AppConfig for apps.dashboard."""

from django.apps import AppConfig


class DashboardConfig(AppConfig):
    """Dashboard configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboard"
