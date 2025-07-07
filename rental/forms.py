from django import forms
from .models import Order, Product, Storage, Shelf
from django.utils import timezone

class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['contact_person', 'phone1', 'phone2', 'rental_start', 'rental_end', 'comment']
        widgets = {
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Введите ФИО'}),
            'phone1': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+7 (999) 123-45-67'}),
            'phone2': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+7 (999) 123-45-67 (необязательно)'}),
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
        fields = ['name', 'photo', 'article', 'description', 'quantity', 'tags', 'daily_price', 'shelf']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'article': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'daily_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tags': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'shelf': forms.Select(attrs={'class': 'form-control'}),
        }
    
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
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Например: A, B, C'})
        }

class ShelfForm(forms.ModelForm):
    class Meta:
        model = Shelf
        fields = ['storage', 'number']
        widgets = {
            'storage': forms.Select(attrs={'class': 'form-control'}),
            'number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Например: 1, 2, 3'})
        }