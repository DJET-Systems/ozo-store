"""URL configuration for the public storefront surface."""

from __future__ import annotations

from django.urls import path

from apps.core.views import healthz, readyz
from apps.storefront import views

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("readyz", readyz, name="readyz"),
    # Catalog & Shopping Flow
    path("", views.home, name="storefront-home"),
    path("c/<slug:slug>/", views.category_view, name="storefront-category"),
    path("p/<slug:handle>/", views.product_detail_view, name="storefront-product-detail"),
    path("cart/", views.cart_view, name="storefront-cart"),
    path("cart/add/", views.cart_add_view, name="storefront-cart-add"),
    path("cart/update/", views.cart_update_view, name="storefront-cart-update"),
    path("checkout/", views.checkout_view, name="storefront-checkout"),
    path(
        "checkout/success/<str:reference>/",
        views.order_confirmation_view,
        name="storefront-order-confirmation",
    ),
    # Public Utility Services
    path("warranty-check/", views.warranty_check_view, name="storefront-warranty-check"),
    path("track/", views.order_track_view, name="storefront-order-track"),
]
