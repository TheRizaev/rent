from django import template

register = template.Library()

@register.filter
def mul(value, arg):
    """Умножает значение на аргумент"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def subtract(value, arg):
    """Вычитает аргумент из значения"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def range_filter(value):
    """Создает range для цикла в шаблоне"""
    try:
        return range(int(value))
    except (ValueError, TypeError):
        return range(0)

@register.filter
def get_item(dictionary, key):
    """Получает элемент из словаря по ключу"""
    return dictionary.get(key)

@register.filter
def div(value, arg):
    """Делит значение на аргумент"""
    try:
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def sub(value, arg):
    """Вычитает аргумент из значения (псевдоним для subtract)"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def add(value, arg):
    """Добавляет аргумент к значению"""
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return 0
    