"""AppConfig for apps.core."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Register core checks and configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"

    def ready(self) -> None:
        """Import system checks on startup."""
        from . import checks  # noqa: F401
