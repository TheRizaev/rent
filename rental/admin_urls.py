from django.urls import path
from . import admin_views

urlpatterns = [
    path('', admin_views.admin_dashboard, name='admin_dashboard'),
    path('orders/', admin_views.admin_orders, name='admin_orders'),
    path('orders/<int:order_id>/', admin_views.admin_order_detail, name='admin_order_detail'),
    path('orders/<int:order_id>/edit/', admin_views.edit_order, name='edit_order'),
    path('orders/<int:order_id>/update-status/', admin_views.update_order_status, name='update_order_status'),
    
    # Управление стойками и полками
    path('storage/', admin_views.storage_management, name='storage_management'),
    path('storage/add/', admin_views.add_storage, name='add_storage'),
    path('storage/<int:storage_id>/edit/', admin_views.edit_storage, name='edit_storage'),
    path('storage/<int:storage_id>/delete/', admin_views.delete_storage, name='delete_storage'),
    path('shelf/<int:shelf_id>/edit/', admin_views.edit_shelf, name='edit_shelf'),
    path('shelf/<int:shelf_id>/delete/', admin_views.delete_shelf, name='delete_shelf'),
    
    # Управление товарами
    path('products/', admin_views.product_management, name='product_management'),
    path('products/add/', admin_views.add_product, name='add_product'),
    path('products/<int:product_id>/edit/', admin_views.edit_product, name='edit_product'),
    path('products/<int:product_id>/delete/', admin_views.delete_product, name='delete_product'),
    path('inventory/', admin_views.inventory_view, name='inventory_view'),
    
    # Создание заявок
    path('create-order/', admin_views.admin_create_order, name='admin_create_order'),
    
    # Управление тегами
    path('tags/', admin_views.tag_management, name='tag_management'),
    path('api/tags/children/', admin_views.get_tag_children, name='get_tag_children'),
    path('api/tags/structure/', admin_views.tag_structure_api, name='tag_structure_api'),
]