"""AppConfig for apps.presets."""

from django.apps import AppConfig


class PresetsConfig(AppConfig):
    """Presets configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.presets"
