"""Combined development URL configuration mounting Storefront (/) and Staff Portal (/staff/)."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, path

from apps.dashboard import auth_views as dash_auth_views
from apps.dashboard import views as dash_views
from config.urls_dashboard import urlpatterns as dashboard_patterns
from config.urls_storefront import urlpatterns as storefront_patterns

urlpatterns: list[URLPattern | URLResolver] = [
    *storefront_patterns,
    # Staff Portal mounted under /staff/ for local development convenience (bin/dev)
    path("staff/", dash_views.today_view, name="dashboard-today"),
    path("staff/auth/login/", dash_auth_views.login_view, name="dashboard-login"),
    path("staff/auth/logout/", dash_auth_views.logout_view, name="dashboard-logout"),
    path(
        "staff/auth/2fa/verify/",
        dash_auth_views.two_factor_verify_view,
        name="dashboard-2fa-verify",
    ),
    path(
        "staff/auth/2fa/setup/", dash_auth_views.two_factor_setup_view, name="dashboard-2fa-setup"
    ),
    path(
        "staff/auth/invite/<str:token>/",
        dash_auth_views.invite_accept_view,
        name="dashboard-invite-accept",
    ),
    path("staff/orders/", dash_views.orders_list_view, name="dashboard-orders"),
    path(
        "staff/orders/<int:order_id>/status/",
        dash_views.order_status_update_view,
        name="dashboard-order-status",
    ),
    path("staff/products/", dash_views.products_list_view, name="dashboard-products"),
    path("staff/products/create/", dash_views.product_create_view, name="dashboard-product-create"),
    path(
        "staff/products/<int:product_id>/status/",
        dash_views.product_status_update_view,
        name="dashboard-product-status",
    ),
    path("staff/inventory/", dash_views.inventory_list_view, name="dashboard-inventory"),
    path("staff/purchasing/", dash_views.purchasing_list_view, name="dashboard-purchasing"),
    path("staff/reports/", dash_views.reports_view, name="dashboard-reports"),
    path("staff/settings/", dash_views.settings_view, name="dashboard-settings"),
    path("staff/members/", dash_views.staff_list_view, name="dashboard-staff"),
    path("staff/members/invite/", dash_views.staff_invite_view, name="dashboard-staff-invite"),
    path("staff/roles/", dash_views.roles_list_view, name="dashboard-roles"),
    path("staff/audit/", dash_views.audit_list_view, name="dashboard-audit"),
    path("staff/export/<str:dataset>/", dash_views.export_data_view, name="dashboard-export"),
    path("staff/barcode-scan/", dash_views.barcode_scan_view, name="dashboard-barcode-scan"),
    path("staff/support/", dash_views.support_view, name="dashboard-support"),
    *dashboard_patterns,
]
