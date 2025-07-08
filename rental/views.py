from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q
from django.utils import timezone
from django.template.loader import render_to_string
from .models import Product, Order, OrderItem, Tag
from .forms import OrderForm
import json
from datetime import datetime, timedelta
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO

def product_list(request):
    products = Product.objects.filter(available_quantity__gt=0)
    tags = Tag.objects.filter(parent=None)
    
    search_query = request.GET.get('search', '')
    tag_filter = request.GET.get('tag', '')
    
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) | 
            Q(article__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    if tag_filter:
        products = products.filter(tags__id=tag_filter)
    
    context = {
        'products': products,
        'tags': tags,
        'search_query': search_query,
        'selected_tag': tag_filter
    }
    return render(request, 'rental/product_list.html', context)

def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    return render(request, 'rental/product_detail.html', {'product': product})

def cart_view(request):
    cart = request.session.get('cart', {})
    cart_items = []
    total = 0
    
    for product_id, item_data in cart.items():
        try:
            product = Product.objects.get(id=product_id)
            
            # Поддержка разных форматов корзины
            if isinstance(item_data, int):
                # Старый формат - только количество
                quantity = item_data
                days = 1
            elif isinstance(item_data, dict):
                # Новый формат - словарь с quantity и days
                quantity = item_data.get('quantity', 1)
                days = item_data.get('days', 1)
            else:
                # Неизвестный формат, пропускаем
                continue
            
            # Рассчитываем стоимость для одного дня (для отображения базовой цены)
            daily_total = product.daily_price * quantity
            # Полная стоимость с учетом дней
            item_total = daily_total * days
            
            cart_items.append({
                'product': product,
                'quantity': quantity,
                'days': days,
                'daily_total': daily_total,
                'total': item_total
            })
            
            # В total храним стоимость за день для совместимости
            total += daily_total
            
        except Product.DoesNotExist:
            # Удаляем несуществующие товары из корзины
            pass
    
    # Очищаем корзину от несуществующих товаров
    valid_cart = {}
    for product_id, item_data in cart.items():
        try:
            Product.objects.get(id=product_id)
            valid_cart[product_id] = item_data
        except Product.DoesNotExist:
            pass
    
    if len(valid_cart) != len(cart):
        request.session['cart'] = valid_cart
        request.session.modified = True
    
    context = {
        'cart_items': cart_items,
        'total': total
    }
    return render(request, 'rental/cart.html', context)

def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'POST':
        quantity = int(request.POST.get('quantity', 1))
        days = int(request.POST.get('days', 1))
        
        if quantity > product.available_quantity:
            messages.error(request, f'Недостаточно товара на складе. Доступно: {product.available_quantity}')
            return redirect('rental:product_detail', product_id=product_id)
        
        cart = request.session.get('cart', {})
        
        # Получаем текущий элемент из корзины
        current_item = cart.get(str(product_id))
        
        # Проверяем формат данных в корзине
        if current_item is None:
            # Товара нет в корзине
            current_quantity = 0
        elif isinstance(current_item, int):
            # Старый формат - только количество
            current_quantity = current_item
        elif isinstance(current_item, dict):
            # Новый формат - словарь с quantity и days
            current_quantity = current_item.get('quantity', 0)
        else:
            # Неизвестный формат
            current_quantity = 0
        
        # Проверяем, не превышает ли общее количество доступное
        if current_quantity + quantity > product.available_quantity:
            messages.error(request, f'Недостаточно товара на складе. Доступно: {product.available_quantity}, уже в корзине: {current_quantity}')
            return redirect('rental:product_detail', product_id=product_id)
        
        # Сохраняем в новом формате
        cart[str(product_id)] = {
            'quantity': current_quantity + quantity,
            'days': days
        }
        
        request.session['cart'] = cart
        request.session.modified = True
        
        messages.success(request, f'{product.name} добавлен в корзину на {days} дней')
        
        return redirect('rental:cart')
    
    return redirect('rental:product_detail', product_id=product_id)

def remove_from_cart(request, product_id):
    cart = request.session.get('cart', {})
    
    if str(product_id) in cart:
        try:
            product = Product.objects.get(id=product_id)
            cart.pop(str(product_id), None)
            request.session['cart'] = cart
            request.session.modified = True
            messages.success(request, f'{product.name} удален из корзины')
        except Product.DoesNotExist:
            cart.pop(str(product_id), None)
            request.session['cart'] = cart
            request.session.modified = True
            messages.success(request, 'Товар удален из корзины')
    else:
        messages.error(request, 'Товар не найден в корзине')
    
    return redirect('rental:cart')

def checkout(request):
    cart = request.session.get('cart', {})
    
    if not cart:
        messages.error(request, 'Корзина пуста')
        return redirect('rental:cart')
    
    # Получаем количество дней из GET параметра
    rental_days = int(request.GET.get('days', 1))
    
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            
            # Рассчитываем общую сумму с учетом дней
            total = 0
            for product_id, item_data in cart.items():
                try:
                    product = Product.objects.get(id=product_id)
                    
                    if isinstance(item_data, int):
                        quantity = item_data
                        days = rental_days
                    else:
                        quantity = item_data.get('quantity', 1)
                        days = item_data.get('days', rental_days)
                    
                    item_total = product.daily_price * quantity * days
                    total += item_total
                except Product.DoesNotExist:
                    pass
            
            # Применяем скидки
            if rental_days >= 30:
                total *= 0.85  # 15% скидка
            elif rental_days >= 14:
                total *= 0.90  # 10% скидка
            elif rental_days >= 7:
                total *= 0.95  # 5% скидка
            
            order.total_amount = total
            order.created_by_admin = request.user.is_staff if request.user.is_authenticated else False
            
            # Если заявка создается админом, автоматически подтверждаем
            if order.created_by_admin:
                order.status = 'confirmed'
            
            order.save()
            
            # Создаем позиции заявки
            for product_id, item_data in cart.items():
                try:
                    product = Product.objects.get(id=product_id)
                    
                    if isinstance(item_data, int):
                        quantity = item_data
                        days = rental_days
                    else:
                        quantity = item_data.get('quantity', 1)
                        days = item_data.get('days', rental_days)
                    
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=quantity,
                        price=product.daily_price * days  # Сохраняем цену с учетом дней
                    )
                    
                    # Если заявка подтверждена, списываем товар
                    if order.status == 'confirmed':
                        product.available_quantity -= quantity
                        product.save()
                        
                except Product.DoesNotExist:
                    pass
            
            # Очищаем корзину
            request.session['cart'] = {}
            
            messages.success(request, 'Заявка успешно создана!')
            return redirect('rental:order_success', order_id=order.id)
    else:
        form = OrderForm()
    
    # Подготавливаем данные корзины для отображения
    cart_items = []
    total = 0
    
    for product_id, item_data in cart.items():
        try:
            product = Product.objects.get(id=product_id)
            
            if isinstance(item_data, int):
                quantity = item_data
                days = rental_days
            else:
                quantity = item_data.get('quantity', 1)
                days = item_data.get('days', rental_days)
            
            item_total = product.daily_price * quantity * days
            cart_items.append({
                'product': product,
                'quantity': quantity,
                'days': days,
                'total': item_total
            })
            total += item_total
        except Product.DoesNotExist:
            pass
    
    # Применяем скидки для отображения
    discount = 0
    if rental_days >= 30:
        discount = 15
    elif rental_days >= 14:
        discount = 10
    elif rental_days >= 7:
        discount = 5
    
    discounted_total = total * (1 - discount / 100) if discount > 0 else total
    
    context = {
        'form': form,
        'cart_items': cart_items,
        'total': total,
        'discounted_total': discounted_total,
        'discount': discount,
        'rental_days': rental_days
    }
    return render(request, 'rental/checkout.html', context)

def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    context = {'order': order}
    return render(request, 'rental/order_success.html', context)

def download_order_pdf(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    # Создаем PDF
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    
    # Заголовок
    p.drawString(50, 750, f"Заявка #{order.id}")
    p.drawString(50, 730, f"Дата создания: {order.created_at.strftime('%d.%m.%Y %H:%M')}")
    p.drawString(50, 710, f"Период аренды: {order.rental_start.strftime('%d.%m.%Y')} - {order.rental_end.strftime('%d.%m.%Y')}")
    p.drawString(50, 690, f"Контактное лицо: {order.contact_person}")
    p.drawString(50, 670, f"Телефон: {order.phone1}")
    if order.phone2:
        p.drawString(50, 650, f"Телефон 2: {order.phone2}")
    
    # Товары
    y = 600
    p.drawString(50, y, "Товары:")
    y -= 20
    
    for item in order.items.all():
        p.drawString(70, y, f"{item.product.name} (арт. {item.product.article})")
        y -= 15
        p.drawString(70, y, f"Количество: {item.quantity}, Цена: {item.price} руб./день")
        y -= 20
    
    p.drawString(50, y-20, f"Общая сумма: {order.total_amount} руб.")
    
    if order.comment:
        p.drawString(50, y-50, f"Комментарий: {order.comment}")
    
    p.showPage()
    p.save()
    
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="order_{order.id}.pdf"'
    
    return response

def update_cart_quantity(request):
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        new_quantity = int(request.POST.get('quantity', 1))
        
        cart = request.session.get('cart', {})
        
        if str(product_id) in cart:
            try:
                product = Product.objects.get(id=product_id)
                
                if new_quantity > product.available_quantity:
                    messages.error(request, f'Недостаточно товара на складе. Доступно: {product.available_quantity}')
                elif new_quantity <= 0:
                    # Удаляем товар из корзины
                    cart.pop(str(product_id), None)
                    messages.success(request, 'Товар удален из корзины')
                else:
                    # Обновляем количество
                    current_item = cart[str(product_id)]
                    
                    if isinstance(current_item, int):
                        # Старый формат - конвертируем в новый
                        cart[str(product_id)] = {
                            'quantity': new_quantity,
                            'days': 1
                        }
                    elif isinstance(current_item, dict):
                        # Новый формат - обновляем количество
                        cart[str(product_id)]['quantity'] = new_quantity
                    else:
                        # Неизвестный формат - создаем новый
                        cart[str(product_id)] = {
                            'quantity': new_quantity,
                            'days': 1
                        }
                    
                    messages.success(request, 'Количество обновлено')
                
                request.session['cart'] = cart
                request.session.modified = True
                
            except Product.DoesNotExist:
                messages.error(request, 'Товар не найден')
        else:
            messages.error(request, 'Товар не найден в корзине')
    
    return redirect('rental:cart')