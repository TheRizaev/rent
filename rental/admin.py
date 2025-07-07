from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Storage(models.Model):
    name = models.CharField(max_length=10, verbose_name='Название стойки')
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Стойка'
        verbose_name_plural = 'Стойки'

class Shelf(models.Model):
    storage = models.ForeignKey(Storage, on_delete=models.CASCADE, verbose_name='Стойка')
    number = models.CharField(max_length=10, verbose_name='Номер полки')
    
    def __str__(self):
        return f"{self.storage.name}{self.number}"
    
    class Meta:
        verbose_name = 'Полка'
        verbose_name_plural = 'Полки'

class Tag(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название тега')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, verbose_name='Родительский тег')
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Тег'
        verbose_name_plural = 'Теги'

class Product(models.Model):
    name = models.CharField(max_length=200, verbose_name='Название')
    photo = models.ImageField(upload_to='products/', verbose_name='Фото')
    article = models.CharField(max_length=50, unique=True, verbose_name='Артикул')
    description = models.TextField(blank=True, verbose_name='Описание')
    quantity = models.IntegerField(default=0, verbose_name='Количество')
    available_quantity = models.IntegerField(default=0, verbose_name='Доступное количество')
    tags = models.ManyToManyField(Tag, blank=True, verbose_name='Теги')
    daily_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена за день')
    shelf = models.ForeignKey(Shelf, on_delete=models.CASCADE, verbose_name='Место хранения')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'

class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Ожидает подтверждения'),
        ('confirmed', 'Подтверждена'),
        ('in_rent', 'В аренде'),
        ('completed', 'Завершена'),
    ]
    
    PAYMENT_CHOICES = [
        ('paid', 'Оплачена'),
        ('unpaid', 'Не оплачена'),
    ]
    
    contact_person = models.CharField(max_length=200, verbose_name='Контактное лицо')
    phone1 = models.CharField(max_length=20, verbose_name='Телефон 1')
    phone2 = models.CharField(max_length=20, blank=True, verbose_name='Телефон 2')
    comment = models.TextField(blank=True, verbose_name='Комментарий')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='Статус')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='unpaid', verbose_name='Оплата')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    rental_start = models.DateField(verbose_name='Начало аренды')
    rental_end = models.DateField(verbose_name='Конец аренды')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Общая сумма')
    created_by_admin = models.BooleanField(default=False, verbose_name='Создана администратором')
    
    def __str__(self):
        return f"Заявка #{self.id} - {self.contact_person}"
    
    class Meta:
        verbose_name = 'Заявка'
        verbose_name_plural = 'Заявки'
        ordering = ['-created_at']

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name='Заявка')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='Товар')
    quantity = models.IntegerField(verbose_name='Количество')
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Цена')
    
    def __str__(self):
        return f"{self.product.name} x {self.quantity}"
    
    class Meta:
        verbose_name = 'Позиция заявки'
        verbose_name_plural = 'Позиции заявки'