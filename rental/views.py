from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.template.loader import render_to_string
from .models import Product, Order, OrderItem, Tag
from .forms import OrderForm
import json
from datetime import datetime, timedelta
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch, cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from io import BytesIO
import os

def preview_page(request):
    return render(request, 'rental/preview.html')

def product_list(request):
    products = Product.objects.all()
    
    sort_preference = request.session.get('tag_sort_preference', 'order')
    
    if sort_preference == 'alphabetical':
        root_tags = Tag.objects.filter(parent=None).order_by('name')
    elif sort_preference == 'creation_date':
        root_tags = Tag.objects.filter(parent=None).order_by('id')
    else:  # order
        root_tags = Tag.objects.filter(parent=None).order_by('order', 'name')
    
    search_query = request.GET.get('search', '')
    tag_filter = request.GET.get('tag', '')
    
    selected_tag = None
    selected_tag_children = []
    
    if search_query:
        search_query = search_query.strip().lower()
        products = products.filter(
            Q(name__contains=search_query) | 
            Q(article__icontains=search_query) |
            Q(description__contains=search_query)
        )
    
    if tag_filter:
        try:
            selected_tag = Tag.objects.get(id=tag_filter)
            descendant_tags = selected_tag.get_descendants()
            all_tags = [selected_tag] + descendant_tags
            products = products.filter(tags__in=all_tags).distinct()
            
            # Получаем дочерние теги для отображения с правильной сортировкой
            if sort_preference == 'alphabetical':
                selected_tag_children = selected_tag.get_children().order_by('name')
            elif sort_preference == 'creation_date':
                selected_tag_children = selected_tag.get_children().order_by('id')
            else:  # order
                selected_tag_children = selected_tag.get_children().order_by('order', 'name')
        except Tag.DoesNotExist:
            pass
    
    products = products.order_by('name')
    
    context = {
        'products': products,
        'root_tags': root_tags,
        'selected_tag': tag_filter,
        'selected_tag_obj': selected_tag,
        'selected_tag_children': selected_tag_children,
        'search_query': search_query
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
            
            # Рассчитываем стоимость (цена за день * количество * дни)
            item_total = product.daily_price * quantity * days
            
            cart_items.append({
                'product': product,
                'quantity': quantity,
                'days': days,
                'total': item_total
            })
            
            total += item_total
            
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
            return redirect(request.META.get('HTTP_REFERER', 'rental:product_detail'), product_id=product_id)
        
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
            return redirect(request.META.get('HTTP_REFERER', 'rental:product_detail'), product_id=product_id)
        
        # Сохраняем в новом формате
        cart[str(product_id)] = {
            'quantity': current_quantity + quantity,
            'days': days
        }
        
        request.session['cart'] = cart
        request.session.modified = True
        
        messages.success(request, f'{product.name} добавлен в корзину на {days} дней')
        
        # Возвращаемся на предыдущую страницу
        referer = request.META.get('HTTP_REFERER')
        if referer:
            return redirect(referer)
        else:
            # Если нет referrer, возвращаемся на страницу товара
            return redirect('rental:product_detail', product_id=product_id)
    
    # Если не POST запрос, возвращаемся на страницу товара
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

def cart_count_api(request):
    """API для получения количества товаров в корзине"""
    cart = request.session.get('cart', {})
    count = len(cart)
    return JsonResponse({'count': count})

def checkout(request):
    cart = request.session.get('cart', {})
    
    if not cart:
        messages.error(request, 'Корзина пуста')
        return redirect('rental:cart')
    
    if request.method == 'POST':
        # Передаем пользователя в форму для определения доступности поля deposit_amount
        form = OrderForm(request.POST, user=request.user)
        if form.is_valid():
            order = form.save(commit=False)
            
            # ИСПРАВЛЕНО: Правильный расчет общей суммы
            total = 0
            rental_days = (order.rental_end - order.rental_start).days + 1
            
            for product_id, item_data in cart.items():
                try:
                    product = Product.objects.get(id=product_id)
                    
                    if isinstance(item_data, int):
                        quantity = item_data
                        days = rental_days  # Используем дни из формы заказа
                    else:
                        quantity = item_data.get('quantity', 1)
                        # Игнорируем дни из корзины, используем дни из заказа
                        days = rental_days
                    
                    # Правильный расчет: цена за день * количество * дни аренды
                    item_total = product.daily_price * quantity * days
                    total += item_total
                except Product.DoesNotExist:
                    pass
            
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
                    else:
                        quantity = item_data.get('quantity', 1)
                    
                    # ИСПРАВЛЕНО: Цена указывается за единицу товара за весь период аренды из заказа
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=quantity,
                        price=product.daily_price * rental_days  # Цена за единицу за весь период
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
        # Передаем пользователя в форму и при GET запросе
        form = OrderForm(user=request.user)
    
    # ИСПРАВЛЕНО: Подготавливаем данные корзины для отображения с правильным расчетом
    cart_items = []
    total = 0
    
    # Получаем предварительные даты из GET параметров или используем значения по умолчанию
    rental_start = request.GET.get('rental_start')
    rental_end = request.GET.get('rental_end')
    
    if rental_start and rental_end:
        try:
            from datetime import datetime
            start_date = datetime.strptime(rental_start, '%Y-%m-%d').date()
            end_date = datetime.strptime(rental_end, '%Y-%m-%d').date()
            rental_days = (end_date - start_date).days + 1
        except:
            rental_days = 1
    else:
        rental_days = 1
    
    for product_id, item_data in cart.items():
        try:
            product = Product.objects.get(id=product_id)
            
            if isinstance(item_data, int):
                quantity = item_data
                # Используем rental_days вместо дней из корзины
                days = rental_days
            else:
                quantity = item_data.get('quantity', 1)
                # Используем rental_days вместо дней из корзины
                days = rental_days
            
            # Правильный расчет
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
    
    context = {
        'form': form,
        'cart_items': cart_items,
        'total': total,
        'rental_days': rental_days
    }
    return render(request, 'rental/checkout.html', context)

def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    context = {'order': order}
    return render(request, 'rental/order_success.html', context)

def download_order_pdf(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    # Импорты для PDF
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase import pdfmetrics
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from django.conf import settings
    
    # Создаем PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, 
                           topMargin=2*cm, bottomMargin=2*cm)
    
    # Регистрируем шрифты из папки static/fonts/
    try:
        # Путь к папке со шрифтами
        fonts_dir = os.path.join(settings.BASE_DIR, 'static', 'fonts')
        
        # Список возможных имен файлов шрифтов
        font_files = [
            'TT.ttf'
        ]
        
        bold_font_files = [
            'TTB.ttf'
        ]
        
        font_registered = False
        bold_font_registered = False
        
        # Пытаемся зарегистрировать обычный шрифт
        for font_file in font_files:
            font_path = os.path.join(fonts_dir, font_file)
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont('CustomFont', font_path))
                    font_registered = True
                    print(f"Зарегистрирован шрифт: {font_file}")
                    break
                except Exception as e:
                    print(f"Ошибка регистрации шрифта {font_file}: {e}")
                    continue
        
        # Пытаемся зарегистрировать жирный шрифт
        for bold_font_file in bold_font_files:
            bold_font_path = os.path.join(fonts_dir, bold_font_file)
            if os.path.exists(bold_font_path):
                try:
                    pdfmetrics.registerFont(TTFont('CustomFont-Bold', bold_font_path))
                    bold_font_registered = True
                    print(f"Зарегистрирован жирный шрифт: {bold_font_file}")
                    break
                except Exception as e:
                    print(f"Ошибка регистрации жирного шрифта {bold_font_file}: {e}")
                    continue
        
        # Устанавливаем имена шрифтов
        if font_registered:
            font_name = 'CustomFont'
        else:
            font_name = 'Times-Roman'
            print("Используется встроенный шрифт Times-Roman")
            
        if bold_font_registered:
            font_name_bold = 'CustomFont-Bold'
        else:
            font_name_bold = 'Times-Bold'
            print("Используется встроенный жирный шрифт Times-Bold")
            
    except Exception as e:
        print(f"Общая ошибка при работе со шрифтами: {e}")
        # Fallback к встроенным шрифтам
        font_name = 'Times-Roman'
        font_name_bold = 'Times-Bold'
    
    # Стили с поддержкой кириллицы
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=font_name_bold,
        fontSize=18,
        spaceAfter=20,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#2c3e50')
    )
    
    header_style = ParagraphStyle(
        'CustomHeader',
        parent=styles['Heading2'],
        fontName=font_name_bold,
        fontSize=14,
        spaceAfter=12,
        textColor=colors.HexColor('#34495e')
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName=font_name,
        fontSize=10,
        spaceAfter=4
    )
    
    # Элементы документа
    story = []
    
    # Заголовок
    title_text = f"ЗАЯВКА НА АРЕНДУ ОБОРУДОВАНИЯ № {order.id}"
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 15))
    
    # Информация о заявке
    story.append(Paragraph("ИНФОРМАЦИЯ О ЗАЯВКЕ", header_style))
    
    info_data = [
        ['Дата создания:', order.created_at.strftime('%d.%m.%Y %H:%M')],
        ['Период аренды:', f"{order.rental_start.strftime('%d.%m.%Y')} - {order.rental_end.strftime('%d.%m.%Y')}"],
        ['Контактное лицо:', order.contact_person],
        ['Телефон:', order.phone1],
        ['Статус заявки:', order.get_status_display()],
        ['Статус оплаты:', order.get_payment_status_display()],
    ]
    
    if order.phone2:
        info_data.insert(4, ['Телефон 2:', order.phone2])
    
    if order.comment:
        info_data.insert(-2, ['Комментарий:', order.get_display_comment()])
    
    if order.created_by_admin:
        info_data.insert(-2, ['Создана администратором:', 'Да'])
    
    # Таблица с информацией (увеличиваем размеры)
    info_table = Table(info_data, colWidths=[5*cm, 13*cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (0, -1), font_name_bold),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
    ]))
    
    story.append(info_table)
    story.append(Spacer(1, 20))
    
    # Товары
    story.append(Paragraph("ТОВАРЫ В ЗАЯВКЕ", header_style))
    
    # Заголовки таблицы товаров
    items_data = [['№', 'Наименование', 'Артикул', 'Штрих-код', 'Кол-во', 'Цена/период', 'Сумма', 'Место']]
    
    total_sum = 0
    for i, item in enumerate(order.items.all(), 1):
        item_total = item.price * item.quantity
        total_sum += item_total
        
        # Обрезаем длинные названия
        name = item.product.get_display_name()
        if len(name) > 20:
            name = name[:20] + '...'
        
        items_data.append([
            str(i),
            name,
            item.product.article,
            getattr(item.product, 'barcode', '-'),  # Добавляем штрих-код
            f"{item.quantity} шт.",
            f"{item.price:.0f} сум",
            f"{item_total:.0f} сум",
            str(item.product.shelf)
        ])
    
    # Добавляем итоговую строку
    items_data.append(['', '', '', '', '', 'ИТОГО:', f"{order.total_amount:.0f} сум", ''])
    
    # Увеличиваем размеры таблицы товаров для штрих-кода
    items_table = Table(items_data, colWidths=[0.8*cm, 3.5*cm, 2*cm, 2.5*cm, 1.5*cm, 2.2*cm, 2.2*cm, 1.8*cm])
    items_table.setStyle(TableStyle([
        # Заголовок
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), font_name_bold),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        
        # Содержимое
        ('FONTNAME', (0, 1), (-1, -2), font_name),
        ('FONTSIZE', (0, 1), (-1, -2), 7),
        ('ALIGN', (0, 1), (0, -2), 'CENTER'),  # Номера по центру
        ('ALIGN', (2, 1), (-1, -2), 'CENTER'),  # Числа и коды по центру
        ('ALIGN', (1, 1), (1, -2), 'LEFT'),    # Названия слева
        
        # Итоговая строка
        ('FONTNAME', (0, -1), (-1, -1), font_name_bold),
        ('FONTSIZE', (0, -1), (-1, -1), 10),
        ('ALIGN', (0, -1), (-1, -1), 'CENTER'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ecf0f1')),
        ('SPAN', (0, -1), (5, -1)),  # Объединяем ячейки для "ИТОГО"
        
        # Сетка
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        
        # Отступы
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    story.append(items_table)
    story.append(Spacer(1, 20))
    
    # Дополнительная информация
    story.append(Paragraph("ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ", header_style))
    
    # Рассчитываем количество дней аренды
    rental_days = (order.rental_end - order.rental_start).days + 1
    
    additional_info = [
        ['Количество дней аренды:', f"{rental_days} дн."],
        ['Средняя стоимость в день:', f"{order.total_amount / rental_days:.0f} сум/день"],
        ['Общая сумма:', f"{order.total_amount:.0f} сум"],
    ]
    
    additional_table = Table(additional_info, colWidths=[6*cm, 8*cm])
    additional_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (0, -1), font_name_bold),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8f9fa')),
    ]))
    
    story.append(additional_table)
    story.append(Spacer(1, 30))
    
    # Подпись
    footer_style = ParagraphStyle(
        'Footer', 
        parent=styles['Normal'], 
        fontSize=8,
        fontName=font_name,
        textColor=colors.grey, 
        alignment=TA_RIGHT
    )
    
    footer_text = f"Дата формирования документа: {(timezone.now() + timedelta(hours=5)).strftime('%d.%m.%Y %H:%M')}"
    story.append(Paragraph(footer_text, footer_style))
    
    # Генерируем PDF
    try:
        doc.build(story)
        print("PDF успешно создан")
    except Exception as e:
        print(f"Ошибка при создании PDF: {e}")
        # Создаем упрощенный PDF как fallback
        buffer.seek(0)
        buffer.truncate()
        
        from reportlab.pdfgen import canvas
        p = canvas.Canvas(buffer, pagesize=A4)
        
        # Простой текстовый PDF
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, 800, f"ЗАЯВКА НА АРЕНДУ ОБОРУДОВАНИЯ № {order.id}")
        
        p.setFont("Helvetica", 10)
        y = 750
        p.drawString(50, y, f"Дата создания: {order.created_at.strftime('%d.%m.%Y %H:%M')}")
        y -= 20
        p.drawString(50, y, f"Контактное лицо: {order.contact_person}")
        y -= 20
        p.drawString(50, y, f"Телефон: {order.phone1}")
        y -= 20
        p.drawString(50, y, f"Период аренды: {order.rental_start.strftime('%d.%m.%Y')} - {order.rental_end.strftime('%d.%m.%Y')}")
        y -= 20
        p.drawString(50, y, f"Общая сумма: {order.total_amount} сум")
        
        y -= 40
        p.drawString(50, y, "ТОВАРЫ:")
        y -= 20
        
        for i, item in enumerate(order.items.all(), 1):
            if y < 50:  # Проверяем, не достигли ли низа страницы
                p.showPage()
                y = 800
            p.drawString(70, y, f"{i}. {item.product.name} - {item.quantity} шт. - {item.get_total()} сум")
            y -= 15
        
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

def update_cart_days(request):
    product_id = request.GET.get('product_id')
    new_days = request.GET.get('days')
    
    if not product_id or not new_days:
        messages.error(request, 'Неверные параметры')
        return redirect('rental:cart')
    
    try:
        new_days = int(new_days)
        if new_days < 1 or new_days > 365:
            messages.error(request, 'Количество дней должно быть от 1 до 365')
            return redirect('rental:cart')
    except (ValueError, TypeError):
        messages.error(request, 'Неверное количество дней')
        return redirect('rental:cart')
    
    cart = request.session.get('cart', {})
    
    if str(product_id) in cart:
        try:
            product = Product.objects.get(id=product_id)
            
            # Обновляем количество дней
            current_item = cart[str(product_id)]
            
            if isinstance(current_item, int):
                # Старый формат - конвертируем в новый
                cart[str(product_id)] = {
                    'quantity': current_item,
                    'days': new_days
                }
            elif isinstance(current_item, dict):
                # Новый формат - обновляем дни
                cart[str(product_id)]['days'] = new_days
            else:
                # Неизвестный формат - создаем новый
                cart[str(product_id)] = {
                    'quantity': 1,
                    'days': new_days
                }
            
            request.session['cart'] = cart
            request.session.modified = True
            
            messages.success(request, f'Количество дней для "{product.name}" изменено на {new_days}')
            
        except Product.DoesNotExist:
            messages.error(request, 'Товар не найден')
    else:
        messages.error(request, 'Товар не найден в корзине')
    
    return redirect('rental:cart')