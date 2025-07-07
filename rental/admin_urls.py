from django.urls import path
from . import admin_views

urlpatterns = [
    path('', admin_views.admin_dashboard, name='admin_dashboard'),
    path('orders/', admin_views.admin_orders, name='admin_orders'),
    path('orders/<int:order_id>/', admin_views.admin_order_detail, name='admin_order_detail'),
    path('orders/<int:order_id>/update-status/', admin_views.update_order_status, name='update_order_status'),
    path('storage/', admin_views.storage_management, name='storage_management'),
    path('storage/add/', admin_views.add_storage, name='add_storage'),
    path('products/', admin_views.product_management, name='product_management'),
    path('products/add/', admin_views.add_product, name='add_product'),
    path('products/<int:product_id>/edit/', admin_views.edit_product, name='edit_product'),
    path('inventory/', admin_views.inventory_view, name='inventory_view'),
    path('create-order/', admin_views.admin_create_order, name='admin_create_order'),
]