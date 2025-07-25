from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from .models import Product, Order, OrderItem, Storage, Shelf, Tag
from .forms import ProductForm, StorageForm, ShelfForm, OrderForm
import json
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from io import BytesIO
import barcode
from barcode.writer import ImageWriter
from PIL import Image
import qrcode

def is_admin(user):
    return user.is_authenticated and user.is_staff

@user_passes_test(is_admin)
def admin_dashboard(request):
    # Статистика для дашборда
    total_products = Product.objects.count()
    pending_orders = Order.objects.filter(status='pending').count()
    confirmed_orders = Order.objects.filter(status='confirmed').count()
    rejected_orders = Order.objects.filter(status='rejected').count()
    total_revenue = sum(order.total_amount for order in Order.objects.filter(payment_status='paid'))
    
    recent_orders = Order.objects.all()[:5]
    
    context = {
        'total_products': total_products,
        'pending_orders': pending_orders,
        'confirmed_orders': confirmed_orders,
        'rejected_orders': rejected_orders,
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
        search_query = search_query.strip()
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
        
        # Проверяем, не пытается ли пользователь изменить завершенную или отклоненную заявку
        if order.status in ['completed', 'rejected'] and new_status:
            return JsonResponse({
                'success': False, 
                'error': 'Нельзя изменить статус завершенной или отклоненной заявки!'
            })
        
        old_status = order.status
        
        # Обрабатываем изменение статуса только если он передан и заявка не завершена/отклонена
        if new_status and old_status not in ['completed', 'rejected']:
            # Логика изменения статусов с правильным управлением товарами
            if old_status == 'pending' and new_status == 'confirmed':
                # Проверяем доступность всех товаров
                for item in order.items.all():
                    if item.product.available_quantity < item.quantity:
                        return JsonResponse({
                            'success': False,
                            'error': f'Недостаточно товара "{item.product.name}" на складе. Доступно: {item.product.available_quantity}, требуется: {item.quantity}'
                        })
                
                # Если все товары доступны, списываем их
                for item in order.items.all():
                    product = item.product
                    product.available_quantity -= item.quantity
                    product.save()
                    
            elif old_status == 'confirmed' and new_status == 'completed':
                # При завершении возвращаем товары на склад
                for item in order.items.all():
                    product = item.product
                    product.available_quantity += item.quantity
                    product.save()
                    
            elif old_status == 'confirmed' and new_status == 'pending':
                # Возврат товаров при откате подтверждения
                for item in order.items.all():
                    product = item.product
                    product.available_quantity += item.quantity
                    product.save()
                    
            elif old_status == 'pending' and new_status == 'rejected':
                # При отклонении из ожидания товары не нужно возвращать (их и не списывали)
                pass
                
            elif old_status == 'confirmed' and new_status == 'rejected':
                # При отклонении из подтвержденного состояния возвращаем товары
                for item in order.items.all():
                    product = item.product
                    product.available_quantity += item.quantity
                    product.save()
            
            order.status = new_status
        
        # Статус оплаты можно менять всегда, вне зависимости от статуса заявки
        if new_payment_status:
            order.payment_status = new_payment_status
        
        order.save()
        
        return JsonResponse({'success': True})
    
    return JsonResponse({'success': False})

@user_passes_test(is_admin)
def storage_management(request):
    storages = Storage.objects.all()
    shelves = Shelf.objects.all().select_related('storage')
    
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
        
        elif 'edit_storage' in request.POST:
            storage_id = request.POST.get('storage_id')
            name = request.POST.get('name')
            try:
                storage = Storage.objects.get(id=storage_id)
                storage.name = name
                storage.save()
                messages.success(request, f'Стойка "{name}" обновлена')
            except Storage.DoesNotExist:
                messages.error(request, 'Стойка не найдена')
            return redirect('storage_management')
        
        elif 'edit_shelf' in request.POST:
            shelf_id = request.POST.get('shelf_id')
            storage_id = request.POST.get('storage_id')
            number = request.POST.get('number')
            try:
                shelf = Shelf.objects.get(id=shelf_id)
                storage = Storage.objects.get(id=storage_id)
                shelf.storage = storage
                shelf.number = number
                shelf.save()
                messages.success(request, f'Полка "{shelf}" обновлена')
            except (Shelf.DoesNotExist, Storage.DoesNotExist):
                messages.error(request, 'Полка или стойка не найдена')
            return redirect('storage_management')
        
        elif 'delete_storage' in request.POST:
            storage_id = request.POST.get('storage_id')
            try:
                storage = Storage.objects.get(id=storage_id)
                storage_name = storage.name
                
                # Проверяем, есть ли полки в этой стойке
                shelves_count = storage.shelf_set.count()
                if shelves_count > 0:
                    messages.error(request, f'Нельзя удалить стойку "{storage_name}": в ней есть {shelves_count} полок')
                else:
                    storage.delete()
                    messages.success(request, f'Стойка "{storage_name}" удалена')
            except Storage.DoesNotExist:
                messages.error(request, 'Стойка не найдена')
            return redirect('storage_management')
        
        elif 'delete_shelf' in request.POST:
            shelf_id = request.POST.get('shelf_id')
            try:
                shelf = Shelf.objects.get(id=shelf_id)
                shelf_name = str(shelf)
                
                # Проверяем, есть ли товары на этой полке
                products_count = shelf.product_set.count()
                if products_count > 0:
                    messages.error(request, f'Нельзя удалить полку "{shelf_name}": на ней находится {products_count} товаров')
                else:
                    shelf.delete()
                    messages.success(request, f'Полка "{shelf_name}" удалена')
            except Shelf.DoesNotExist:
                messages.error(request, 'Полка не найдена')
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
        search_query = search_query.strip()
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
def delete_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'POST':
        # Проверяем, используется ли товар в активных заявках
        active_orders = OrderItem.objects.filter(
            product=product,
            order__status__in=['pending', 'confirmed']
        ).count()
        
        if active_orders > 0:
            messages.error(request, f'Нельзя удалить товар "{product.name}": он используется в {active_orders} активных заявках')
        else:
            product_name = product.name
            product.delete()
            messages.success(request, f'Товар "{product_name}" успешно удален')
        
        return redirect('product_management')
    
    # Подсчитываем использование товара
    active_orders = OrderItem.objects.filter(
        product=product,
        order__status__in=['pending', 'confirmed']
    ).count()
    
    context = {
        'product': product,
        'active_orders': active_orders,
    }
    return render(request, 'rental/admin/confirm_delete_product.html', context)

@user_passes_test(is_admin)
def inventory_view(request):
    products = Product.objects.all()
    
    search_query = request.GET.get('search', '')
    if search_query:
        search_query = search_query.strip()
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
            order.status = 'confirmed' 
            
            cart_data = request.POST.get('cart_data', '[]')
            cart_items = json.loads(cart_data)
            
            for item in cart_items:
                try:
                    product = Product.objects.get(id=item['product_id'])
                    if product.available_quantity < item['quantity']:
                        messages.error(request, f'Недостаточно товара "{product.name}" на складе. Доступно: {product.available_quantity}')
                        return render(request, 'rental/admin/create_order.html', {
                            'form': form,
                            'products': Product.objects.filter(available_quantity__gt=0)
                        })
                except Product.DoesNotExist:
                    messages.error(request, 'Один из товаров не найден')
                    return render(request, 'rental/admin/create_order.html', {
                        'form': form,
                        'products': Product.objects.filter(available_quantity__gt=0)
                    })
            
            total = 0
            rental_days = (order.rental_end - order.rental_start).days + 1
            
            for item in cart_items:
                try:
                    product = Product.objects.get(id=item['product_id'])
                    total += product.daily_price * item['quantity'] * rental_days
                except Product.DoesNotExist:
                    pass
            
            order.total_amount = total
            order.save()
            
            for item in cart_items:
                try:
                    product = Product.objects.get(id=item['product_id'])
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=item['quantity'],
                        price=product.daily_price * rental_days
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
    
    products = Product.objects.all().order_by('name')
    
    context = {
        'form': form,
        'products': products,
    }
    return render(request, 'rental/admin/create_order.html', context)

@user_passes_test(is_admin)
def tag_management(request):
    if request.method == 'POST':
        if 'add_tag' in request.POST:
            name = request.POST.get('name')
            parent_id = request.POST.get('parent')
            
            if name:
                parent = None
                if parent_id:
                    try:
                        parent = Tag.objects.get(id=parent_id)
                    except Tag.DoesNotExist:
                        pass
                
                Tag.objects.create(name=name, parent=parent)
                messages.success(request, f'Тег "{name}" успешно добавлен')
                return redirect('tag_management')
        
        elif 'edit_tag' in request.POST:
            tag_id = request.POST.get('tag_id')
            name = request.POST.get('name')
            parent_id = request.POST.get('parent')
            
            try:
                tag = Tag.objects.get(id=tag_id)
                tag.name = name
                
                # Проверяем, что родительский тег не является потомком текущего тега
                if parent_id:
                    parent = Tag.objects.get(id=parent_id)
                    if not tag.is_ancestor_of(parent) and parent.id != tag.id:
                        tag.parent = parent
                    else:
                        messages.error(request, 'Нельзя сделать потомка родителем его предка')
                        return redirect('tag_management')
                else:
                    tag.parent = None
                
                tag.save()
                messages.success(request, f'Тег "{name}" успешно обновлен')
            except Tag.DoesNotExist:
                messages.error(request, 'Тег не найден')
            except Exception as e:
                messages.error(request, f'Ошибка при обновлении тега: {e}')
            
            return redirect('tag_management')
        
        elif 'delete_tag' in request.POST:
            tag_id = request.POST.get('tag_id')
            try:
                tag = Tag.objects.get(id=tag_id)
                tag_name = tag.name
                
                # Проверяем, есть ли товары с этим тегом
                products_count = tag.product_set.count()
                children_count = tag.tag_set.count()
                
                if products_count > 0:
                    messages.error(request, f'Нельзя удалить тег "{tag_name}": используется в {products_count} товарах')
                elif children_count > 0:
                    messages.error(request, f'Нельзя удалить тег "{tag_name}": у него есть {children_count} дочерних тегов')
                else:
                    tag.delete()
                    messages.success(request, f'Тег "{tag_name}" успешно удален')
            except Tag.DoesNotExist:
                messages.error(request, 'Тег не найден')
            
            return redirect('tag_management')
    
    # Получаем все теги и сортируем их вручную
    all_tags = Tag.objects.all()
    
    # Группируем теги по уровням для отображения
    root_tags = all_tags.filter(parent=None).order_by('name')
    tag_tree = []
    
    def build_tree(parent_tags, level=0):
        tree = []
        for tag in parent_tags.order_by('name'):
            tree.append({
                'tag': tag,
                'level': level,
                'products_count': tag.product_set.count(),
                'children_count': tag.tag_set.count()
            })
            children = all_tags.filter(parent=tag)
            if children:
                tree.extend(build_tree(children, level + 1))
        return tree
    
    tag_tree = build_tree(root_tags)
    
    context = {
        'tags': all_tags.order_by('name'),
        'tag_tree': tag_tree,
        'root_tags': root_tags,
    }
    return render(request, 'rental/admin/tag_management.html', context)

@user_passes_test(is_admin)
def get_tag_children(request):
    """API endpoint для получения дочерних тегов"""
    parent_id = request.GET.get('parent_id')
    
    if parent_id:
        try:
            parent = Tag.objects.get(id=parent_id)
            children = parent.tag_set.all().order_by('name').values('id', 'name')
            return JsonResponse({
                'success': True,
                'children': list(children)
            })
        except Tag.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Родительский тег не найден'})
    else:
        # Возвращаем корневые теги
        root_tags = Tag.objects.filter(parent=None).order_by('name').values('id', 'name')
        return JsonResponse({
            'success': True,
            'children': list(root_tags)
        })

@user_passes_test(is_admin)
def tag_structure_api(request):
    """API для получения структуры тегов в JSON формате"""
    def build_json_tree(parent=None):
        tags = Tag.objects.filter(parent=parent).order_by('name')
        tree = []
        for tag in tags:
            children = build_json_tree(tag)
            tree.append({
                'id': tag.id,
                'name': tag.name,
                'products_count': tag.product_set.count(),
                'children': children
            })
        return tree
    
    tree = build_json_tree()
    return JsonResponse({'tree': tree})

@user_passes_test(is_admin)
def edit_storage(request, storage_id):
    storage = get_object_or_404(Storage, id=storage_id)
    
    if request.method == 'POST':
        form = StorageForm(request.POST, instance=storage)
        if form.is_valid():
            form.save()
            messages.success(request, f'Стойка "{storage.name}" обновлена')
            return redirect('storage_management')
    else:
        form = StorageForm(instance=storage)
    
    context = {
        'form': form,
        'storage': storage,
    }
    return render(request, 'rental/admin/edit_storage.html', context)

@user_passes_test(is_admin)
def edit_shelf(request, shelf_id):
    shelf = get_object_or_404(Shelf, id=shelf_id)
    
    if request.method == 'POST':
        form = ShelfForm(request.POST, instance=shelf)
        if form.is_valid():
            form.save()
            messages.success(request, f'Полка "{shelf}" обновлена')
            return redirect('storage_management')
    else:
        form = ShelfForm(instance=shelf)
    
    context = {
        'form': form,
        'shelf': shelf,
    }
    return render(request, 'rental/admin/edit_shelf.html', context)

@user_passes_test(is_admin)
def delete_storage(request, storage_id):
    storage = get_object_or_404(Storage, id=storage_id)
    
    if request.method == 'POST':
        shelves_count = storage.shelf_set.count()
        if shelves_count > 0:
            messages.error(request, f'Нельзя удалить стойку "{storage.name}": в ней есть {shelves_count} полок')
        else:
            storage_name = storage.name
            storage.delete()
            messages.success(request, f'Стойка "{storage_name}" удалена')
        return redirect('storage_management')
    
    context = {
        'storage': storage,
        'shelves_count': storage.shelf_set.count(),
    }
    return render(request, 'rental/admin/confirm_delete_storage.html', context)

@user_passes_test(is_admin)
def delete_shelf(request, shelf_id):
    shelf = get_object_or_404(Shelf, id=shelf_id)
    
    if request.method == 'POST':
        products_count = shelf.product_set.count()
        if products_count > 0:
            messages.error(request, f'Нельзя удалить полку "{shelf}": на ней находится {products_count} товаров')
        else:
            shelf_name = str(shelf)
            shelf.delete()
            messages.success(request, f'Полка "{shelf_name}" удалена')
        return redirect('storage_management')
    
    context = {
        'shelf': shelf,
        'products_count': shelf.product_set.count(),
    }
    return render(request, 'rental/admin/confirm_delete_shelf.html', context)

@user_passes_test(is_admin)
def edit_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    # Проверяем, что заявка в статусе ожидания
    if order.status != 'pending':
        messages.error(request, 'Можно редактировать только заявки в статусе "Ожидает подтверждения"')
        return redirect('admin_order_detail', order_id=order.id)
    
    if request.method == 'POST':
        form = OrderForm(request.POST, instance=order)
        if form.is_valid():
            order = form.save(commit=False)
            
            # Получаем товары из POST данных
            cart_data = request.POST.get('cart_data', '[]')
            cart_items = json.loads(cart_data)
            
            # ВАЖНО: При редактировании pending заявки товары НЕ БЫЛИ списаны с available_quantity
            # поэтому мы НЕ возвращаем их на склад, просто удаляем старые позиции заявки
            
            # Сохраняем информацию о старых товарах для правильного расчета доступности
            old_items = {}
            for item in order.items.all():
                old_items[item.product.id] = item.quantity
            
            # Удаляем старые позиции заявки
            order.items.all().delete()
            
            # Проверяем доступность новых товаров
            for item in cart_items:
                try:
                    product = Product.objects.get(id=item['product_id'])
                    
                    # При проверке доступности учитываем, что старые товары не были списаны
                    # available_quantity уже включает в себя товары из старой заявки
                    if product.available_quantity < item['quantity']:
                        messages.error(request, f'Недостаточно товара "{product.name}" на складе. Доступно: {product.available_quantity}, требуется: {item["quantity"]}')
                        
                        # Восстанавливаем старые позиции заявки
                        for old_product_id, old_quantity in old_items.items():
                            try:
                                old_product = Product.objects.get(id=old_product_id)
                                OrderItem.objects.create(
                                    order=order,
                                    product=old_product,
                                    quantity=old_quantity,
                                    price=old_product.daily_price * ((order.rental_end - order.rental_start).days + 1)
                                )
                            except Product.DoesNotExist:
                                pass
                        
                        return render(request, 'rental/admin/edit_order.html', {
                            'form': form,
                            'order': order,
                            'products': Product.objects.all(),
                            'current_items': []
                        })
                except Product.DoesNotExist:
                    messages.error(request, 'Один из товаров не найден')
                    return render(request, 'rental/admin/edit_order.html', {
                        'form': form,
                        'order': order,
                        'products': Product.objects.all(),
                        'current_items': []
                    })
            
            # Рассчитываем общую сумму
            total = 0
            rental_days = (order.rental_end - order.rental_start).days + 1
            
            for item in cart_items:
                try:
                    product = Product.objects.get(id=item['product_id'])
                    total += product.daily_price * item['quantity'] * rental_days
                except Product.DoesNotExist:
                    pass
            
            order.total_amount = total
            order.save()
            
            # Создаем новые позиции заявки
            for item in cart_items:
                try:
                    product = Product.objects.get(id=item['product_id'])
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=item['quantity'],
                        price=product.daily_price * rental_days  # Цена за единицу за весь период
                    )
                except Product.DoesNotExist:
                    pass
            
            messages.success(request, 'Заявка успешно обновлена!')
            return redirect('admin_order_detail', order_id=order.id)
    else:
        form = OrderForm(instance=order)

    all_products = Product.objects.all()
    
    current_items = []
    for item in order.items.all():
        current_items.append({
            'product_id': item.product.id,
            'name': item.product.get_display_name(),
            'price': float(item.product.daily_price),
            'quantity': item.quantity
        })
    
    
    context = {
        'form': form,
        'order': order,
        'products': all_products,
        'current_items': current_items,
    }
    return render(request, 'rental/admin/edit_order.html', context)

@user_passes_test(is_admin)
def barcode_scanner(request):
    """Страница сканера штрих-кодов"""
    return render(request, 'rental/admin/barcode_scanner.html')

@user_passes_test(is_admin)
@require_http_methods(["POST"])
def barcode_add_to_cart(request):
    """API для добавления товара в корзину по штрих-коду"""
    try:
        data = json.loads(request.body)
        barcode_value = data.get('barcode')
        session_id = data.get('session_id')
        
        if not barcode_value:
            return JsonResponse({'success': False, 'error': 'Штрих-код не указан'})
        
        # Ищем товар по штрих-коду
        try:
            product = Product.objects.get(barcode=barcode_value)
        except Product.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Товар с таким штрих-кодом не найден'})
        
        # Проверяем доступность
        if product.available_quantity <= 0:
            return JsonResponse({'success': False, 'error': 'Товар недоступен'})
        
        # Работаем с корзиной в сессии
        cart_key = f'barcode_cart_{session_id}'
        cart = request.session.get(cart_key, {})
        
        # Добавляем товар в корзину
        product_id_str = str(product.id)
        if product_id_str in cart:
            # Проверяем, не превышаем ли доступное количество
            if cart[product_id_str]['quantity'] >= product.available_quantity:
                return JsonResponse({'success': False, 'error': 'Достигнуто максимальное количество'})
            cart[product_id_str]['quantity'] += 1
        else:
            cart[product_id_str] = {
                'product_id': product.id,
                'name': product.get_display_name(),
                'quantity': 1,
                'price': float(product.daily_price),
                'barcode': product.barcode
            }
        
        request.session[cart_key] = cart
        request.session.modified = True
        
        return JsonResponse({
            'success': True,
            'product_name': product.get_display_name(),
            'cart': cart
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Неверный формат данных'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@user_passes_test(is_admin)
@require_http_methods(["POST"])
def barcode_remove_from_cart(request):
    """API для удаления товара из корзины"""
    try:
        data = json.loads(request.body)
        product_id = data.get('product_id')
        session_id = data.get('session_id')
        
        cart_key = f'barcode_cart_{session_id}'
        cart = request.session.get(cart_key, {})
        
        if str(product_id) in cart:
            del cart[str(product_id)]
            request.session[cart_key] = cart
            request.session.modified = True
            return JsonResponse({'success': True})
        
        return JsonResponse({'success': False, 'error': 'Товар не найден в корзине'})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@user_passes_test(is_admin)
@require_http_methods(["POST"])
def barcode_clear_cart(request):
    """API для очистки корзины"""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        
        cart_key = f'barcode_cart_{session_id}'
        request.session[cart_key] = {}
        request.session.modified = True
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@user_passes_test(is_admin)
def barcode_get_cart(request):
    """API для получения текущей корзины"""
    session_id = request.GET.get('session_id')
    cart_key = f'barcode_cart_{session_id}'
    cart = request.session.get(cart_key, {})
    
    return JsonResponse({'success': True, 'cart': cart})

@user_passes_test(is_admin)
def generate_barcode_image(request, product_id):
    """Генерация изображения штрих-кода для товара"""
    try:
        product = get_object_or_404(Product, id=product_id)
        
        if not product.barcode:
            return HttpResponse('Штрих-код не найден', status=404)
        
        # Генерируем штрих-код
        EAN = barcode.get_barcode_class('ean13')
        ean = EAN(product.barcode, writer=ImageWriter())
        
        # Настройки для изображения
        buffer = BytesIO()
        ean.write(buffer, options={
            'module_width': 0.2,
            'module_height': 15.0,
            'font_size': 10,
            'text_distance': 5.0,
            'quiet_zone': 6.5
        })
        
        buffer.seek(0)
        return HttpResponse(buffer.read(), content_type='image/png')
        
    except Exception as e:
        return HttpResponse(f'Ошибка генерации: {str(e)}', status=500)

@user_passes_test(is_admin)
def download_barcode(request, product_id):
    """Скачать штрих-код как изображение"""
    try:
        product = get_object_or_404(Product, id=product_id)
        
        if not product.barcode:
            return HttpResponse('Штрих-код не найден', status=404)
        
        # Генерируем штрих-код с информацией о товаре
        EAN = barcode.get_barcode_class('ean13')
        ean = EAN(product.barcode, writer=ImageWriter())
        
        # Создаем изображение
        buffer = BytesIO()
        ean.write(buffer, options={
            'module_width': 0.3,
            'module_height': 20.0,
            'font_size': 14,
            'text_distance': 8.0,
            'quiet_zone': 10
        })
        
        # Открываем изображение для добавления дополнительной информации
        buffer.seek(0)
        img = Image.open(buffer)
        
        # Сохраняем финальное изображение
        final_buffer = BytesIO()
        img.save(final_buffer, format='PNG')
        final_buffer.seek(0)
        
        response = HttpResponse(final_buffer.read(), content_type='image/png')
        response['Content-Disposition'] = f'attachment; filename="barcode_{product.article}.png"'
        
        return response
        
    except Exception as e:
        return HttpResponse(f'Ошибка: {str(e)}', status=500)

@user_passes_test(is_admin)
def print_all_barcodes(request):
    """Страница для печати всех штрих-кодов"""
    products = Product.objects.filter(available_quantity__gt=0).order_by('shelf', 'name')
    
    # Группируем по полкам для удобства
    products_by_shelf = {}
    for product in products:
        shelf_key = str(product.shelf)
        if shelf_key not in products_by_shelf:
            products_by_shelf[shelf_key] = []
        products_by_shelf[shelf_key].append(product)
    
    context = {
        'products_by_shelf': products_by_shelf,
    }
    return render(request, 'rental/admin/print_barcodes.html', context)

@user_passes_test(is_admin)
def barcode_lookup(request):
    """API для быстрого поиска товара по штрих-коду"""
    barcode_value = request.GET.get('barcode')
    
    if not barcode_value:
        return JsonResponse({'success': False, 'error': 'Штрих-код не указан'})
    
    try:
        product = Product.objects.get(barcode=barcode_value)
        return JsonResponse({
            'success': True,
            'product': {
                'id': product.id,
                'name': product.get_display_name(),
                'article': product.article,
                'barcode': product.barcode,
                'price': float(product.daily_price),
                'available': product.available_quantity,
                'shelf': str(product.shelf),
                'photo_url': product.photo.url if product.photo else None
            }
        })
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Товар не найден'})
