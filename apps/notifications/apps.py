"""AppConfig for apps.notifications."""

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """Notifications configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.notifications"
