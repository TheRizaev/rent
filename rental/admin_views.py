from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Q
from django.http import JsonResponse
from .models import Product, Order, OrderItem, Storage, Shelf, Tag
from .forms import ProductForm, StorageForm, ShelfForm, OrderForm
import json

def is_admin(user):
    return user.is_authenticated and user.is_staff

@user_passes_test(is_admin)
def admin_dashboard(request):
    # Статистика для дашборда
    total_products = Product.objects.count()
    pending_orders = Order.objects.filter(status='pending').count()
    active_rentals = Order.objects.filter(status='in_rent').count()
    total_revenue = sum(order.total_amount for order in Order.objects.filter(payment_status='paid'))
    
    recent_orders = Order.objects.all()[:5]
    
    context = {
        'total_products': total_products,
        'pending_orders': pending_orders,
        'active_rentals': active_rentals,
        'total_revenue': total_revenue,
        'recent_orders': recent_orders,
    }
    return render(request, 'rental/admin/dashboard.html', context)

@user_passes_test(is_admin)
def admin_orders(request):
    orders = Order.objects.all()
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    search_query = request.GET.get('search', '')
    if search_query:
        orders = orders.filter(
            Q(contact_person__icontains=search_query) |
            Q(phone1__icontains=search_query) |
            Q(id__icontains=search_query)
        )
    
    context = {
        'orders': orders,
        'status_filter': status_filter,
        'search_query': search_query,
    }
    return render(request, 'rental/admin/orders.html', context)

@user_passes_test(is_admin)
def admin_order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    return render(request, 'rental/admin/order_detail.html', {'order': order})

@user_passes_test(is_admin)
def update_order_status(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(Order, id=order_id)
        new_status = request.POST.get('status')
        new_payment_status = request.POST.get('payment_status')
        
        old_status = order.status
        
        if new_status:
            order.status = new_status
            
            # Логика списания/возврата товаров
            if old_status == 'pending' and new_status == 'confirmed':
                # Подтверждение заявки - списываем товары
                for item in order.items.all():
                    product = item.product
                    product.available_quantity -= item.quantity
                    product.save()
                    
            elif old_status == 'in_rent' and new_status == 'completed':
                # Завершение аренды - возвращаем товары
                for item in order.items.all():
                    product = item.product
                    product.available_quantity += item.quantity
                    product.save()
                    
            elif new_status == 'in_rent' and old_status == 'confirmed':
                # Товары уже списаны при подтверждении
                pass
        
        if new_payment_status:
            order.payment_status = new_payment_status
        
        order.save()
        messages.success(request, 'Статус заявки обновлен')
        
        return JsonResponse({'success': True})
    
    return JsonResponse({'success': False})

@user_passes_test(is_admin)
def storage_management(request):
    storages = Storage.objects.all()
    shelves = Shelf.objects.all()
    
    if request.method == 'POST':
        if 'add_storage' in request.POST:
            storage_form = StorageForm(request.POST)
            if storage_form.is_valid():
                storage_form.save()
                messages.success(request, 'Стойка добавлена')
                return redirect('storage_management')
        
        elif 'add_shelf' in request.POST:
            shelf_form = ShelfForm(request.POST)
            if shelf_form.is_valid():
                shelf_form.save()
                messages.success(request, 'Полка добавлена')
                return redirect('storage_management')
    
    storage_form = StorageForm()
    shelf_form = ShelfForm()
    
    context = {
        'storages': storages,
        'shelves': shelves,
        'storage_form': storage_form,
        'shelf_form': shelf_form,
    }
    return render(request, 'rental/admin/storage_management.html', context)

@user_passes_test(is_admin)
def add_storage(request):
    if request.method == 'POST':
        form = StorageForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Стойка успешно добавлена')
            return redirect('storage_management')
    else:
        form = StorageForm()
    
    return render(request, 'rental/admin/add_storage.html', {'form': form})

@user_passes_test(is_admin)
def product_management(request):
    products = Product.objects.all()
    
    search_query = request.GET.get('search', '')
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(article__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    context = {
        'products': products,
        'search_query': search_query,
    }
    return render(request, 'rental/admin/product_management.html', context)

@user_passes_test(is_admin)
def add_product(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Товар успешно добавлен')
            return redirect('product_management')
    else:
        form = ProductForm()
    
    return render(request, 'rental/admin/add_product.html', {'form': form})

@user_passes_test(is_admin)
def edit_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            # Обновляем доступное количество при изменении общего количества
            old_quantity = product.quantity
            new_product = form.save(commit=False)
            quantity_diff = new_product.quantity - old_quantity
            new_product.available_quantity = product.available_quantity + quantity_diff
            new_product.save()
            form.save_m2m()
            
            messages.success(request, 'Товар успешно обновлен')
            return redirect('product_management')
    else:
        form = ProductForm(instance=product)
    
    return render(request, 'rental/admin/edit_product.html', {'form': form, 'product': product})

@user_passes_test(is_admin)
def inventory_view(request):
    products = Product.objects.all()
    
    search_query = request.GET.get('search', '')
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) |
            Q(article__icontains=search_query) |
            Q(shelf__storage__name__icontains=search_query) |
            Q(shelf__number__icontains=search_query)
        )
    
    storage_filter = request.GET.get('storage', '')
    if storage_filter:
        products = products.filter(shelf__storage__name=storage_filter)
    
    storages = Storage.objects.all()
    
    context = {
        'products': products,
        'search_query': search_query,
        'storage_filter': storage_filter,
        'storages': storages,
    }
    return render(request, 'rental/admin/inventory.html', context)

@user_passes_test(is_admin)
def admin_create_order(request):
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.created_by_admin = True
            order.status = 'confirmed'  # Автоматически подтверждаем заявки админа
            
            # Получаем товары из POST данных
            cart_data = request.POST.get('cart_data', '[]')
            cart_items = json.loads(cart_data)
            
            # Рассчитываем общую сумму
            total = 0
            for item in cart_items:
                try:
                    product = Product.objects.get(id=item['product_id'])
                    total += product.daily_price * item['quantity']
                except Product.DoesNotExist:
                    pass
            
            order.total_amount = total
            order.save()
            
            # Создаем позиции заявки и списываем товары
            for item in cart_items:
                try:
                    product = Product.objects.get(id=item['product_id'])
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=item['quantity'],
                        price=product.daily_price
                    )
                    
                    # Списываем товар
                    product.available_quantity -= item['quantity']
                    product.save()
                    
                except Product.DoesNotExist:
                    pass
            
            messages.success(request, 'Заявка успешно создана!')
            return redirect('admin_order_detail', order_id=order.id)
    else:
        form = OrderForm()
    
    products = Product.objects.filter(available_quantity__gt=0)
    
    context = {
        'form': form,
        'products': products,
    }
    return render(request, 'rental/admin/create_order.html', context)