from django import forms
from .models import Order, Product, Storage, Shelf
from django.utils import timezone

class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['contact_person', 'phone1', 'phone2', 'rental_start', 'rental_end', 'comment']
        widgets = {
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Введите ФИО'}),
            'phone1': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+998 (99) 123-45-67'}),
            'phone2': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+998 (99) 123-45-67 (необязательно)'}),
            'rental_start': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'rental_end': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Дополнительная информация (необязательно)'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        rental_start = cleaned_data.get('rental_start')
        rental_end = cleaned_data.get('rental_end')
        
        if rental_start and rental_end:
            if rental_start < timezone.now().date():
                raise forms.ValidationError('Дата начала аренды не может быть в прошлом')
            if rental_end < rental_start:
                raise forms.ValidationError('Дата окончания аренды не может быть раньше даты начала')
        
        return cleaned_data

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'photo', 'barcode', 'description', 'quantity', 'tags', 'daily_price', 'shelf']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'barcode': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Оставьте пустым для автоматической генерации',
                'maxlength': '13'
            }),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'daily_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tags': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
            'shelf': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Делаем поле штрих-кода необязательным
        self.fields['barcode'].required = False
        
        # Добавляем help_text для поля штрих-кода
        self.fields['barcode'].help_text = 'Штрих-код будет использован как артикул. При пустом поле генерируется автоматически.'
        
        if self.instance and self.instance.pk:
            self.initial['name'] = self.instance.get_display_name()
            self.initial['description'] = self.instance.get_display_description()
    
    def clean_barcode(self):
        barcode = self.cleaned_data.get('barcode')
        
        if barcode:
            # Проверяем, что штрих-код состоит из 13 цифр
            if not barcode.isdigit() or len(barcode) != 13:
                raise forms.ValidationError('Штрих-код должен состоять из 13 цифр')
            
            # Проверяем уникальность
            if self.instance.pk:
                if Product.objects.filter(barcode=barcode).exclude(pk=self.instance.pk).exists():
                    raise forms.ValidationError('Товар с таким штрих-кодом уже существует')
            else:
                if Product.objects.filter(barcode=barcode).exists():
                    raise forms.ValidationError('Товар с таким штрих-кодом уже существует')
        
        return barcode
    
    def save(self, commit=True):
        product = super().save(commit=False)
        if not product.id:  # Новый товар
            product.available_quantity = product.quantity
        if commit:
            product.save()
            self.save_m2m()
        return product


class StorageForm(forms.ModelForm):
    class Meta:
        model = Storage
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Например: A, B, C',
                'maxlength': '10'
            })
        }
    
    def clean_name(self):
        name = self.cleaned_data['name'].strip().upper()
        
        # Проверяем уникальность только если это новая стойка или имя изменилось
        if self.instance.pk:
            if Storage.objects.filter(name=name).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError(f'Стойка с названием "{name}" уже существует')
        else:
            if Storage.objects.filter(name=name).exists():
                raise forms.ValidationError(f'Стойка с названием "{name}" уже существует')
        
        return name

class ShelfForm(forms.ModelForm):
    class Meta:
        model = Shelf
        fields = ['storage', 'number']
        widgets = {
            'storage': forms.Select(attrs={'class': 'form-control'}),
            'number': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Например: 1, 2, 3',
                'maxlength': '10'
            })
        }
    
    def clean(self):
        cleaned_data = super().clean()
        storage = cleaned_data.get('storage')
        number = cleaned_data.get('number')
        
        if storage and number:
            number = number.strip()
            
            # Проверяем уникальность комбинации стойка+номер
            if self.instance.pk:
                if Shelf.objects.filter(storage=storage, number=number).exclude(pk=self.instance.pk).exists():
                    raise forms.ValidationError(f'Полка "{number}" уже существует в стойке "{storage.name}"')
            else:
                if Shelf.objects.filter(storage=storage, number=number).exists():
                    raise forms.ValidationError(f'Полка "{number}" уже существует в стойке "{storage.name}"')
            
            cleaned_data['number'] = number
        
        return cleaned_data
    