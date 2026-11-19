"""AppConfig for apps.presets."""

from django.apps import AppConfig


class PresetsConfig(AppConfig):
    """Presets configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.presets"

    def ready(self) -> None:
        """Register preset/brand system checks."""
        from apps.presets import checks  # noqa: F401
