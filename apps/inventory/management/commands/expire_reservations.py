"""Periodic job to expire stale stock reservations."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.inventory.services import expire_stale_reservations


class Command(BaseCommand):
    """Expire stock reservations whose timeout has elapsed and restore available stock."""

    help = "Expire and release stale reservations."

    def handle(self, *args: Any, **options: Any) -> None:
        released = expire_stale_reservations()
        if released:
            self.stdout.write(
                self.style.SUCCESS(f"Successfully released {released} expired reservation(s).")
            )
        else:
            self.stdout.write("No expired reservations found.")
