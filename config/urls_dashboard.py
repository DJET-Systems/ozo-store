"""URL configuration for the merchant dashboard surface."""

from __future__ import annotations

from django.urls import path

from apps.core.views import healthz, readyz
from apps.dashboard import auth_views, views

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    # Staff Auth & Lifecycle
    path("auth/login/", auth_views.login_view, name="dashboard-login"),
    path("auth/logout/", auth_views.logout_view, name="dashboard-logout"),
    path("auth/2fa/verify/", auth_views.two_factor_verify_view, name="dashboard-2fa-verify"),
    path("auth/2fa/setup/", auth_views.two_factor_setup_view, name="dashboard-2fa-setup"),
    path("auth/invite/<str:token>/", auth_views.invite_accept_view, name="dashboard-invite-accept"),
    # Operational Dashboard
    path("", views.today_view, name="dashboard-today"),
    path("orders/", views.orders_list_view, name="dashboard-orders"),
    path(
        "orders/<int:order_id>/status/",
        views.order_status_update_view,
        name="dashboard-order-status",
    ),
    path("products/", views.products_list_view, name="dashboard-products"),
    path("products/create/", views.product_create_view, name="dashboard-product-create"),
    path(
        "products/<int:product_id>/status/",
        views.product_status_update_view,
        name="dashboard-product-status",
    ),
    path("inventory/", views.inventory_list_view, name="dashboard-inventory"),
    path("purchasing/", views.purchasing_list_view, name="dashboard-purchasing"),
    path("reports/", views.reports_view, name="dashboard-reports"),
    path("settings/", views.settings_view, name="dashboard-settings"),
    path("staff/", views.staff_list_view, name="dashboard-staff"),
    path("staff/invite/", views.staff_invite_view, name="dashboard-staff-invite"),
    path("roles/", views.roles_list_view, name="dashboard-roles"),
    path("audit/", views.audit_list_view, name="dashboard-audit"),
    path("export/<str:dataset>/", views.export_data_view, name="dashboard-export"),
    path("barcode-scan/", views.barcode_scan_view, name="dashboard-barcode-scan"),
    path("support/", views.support_view, name="dashboard-support"),
]
