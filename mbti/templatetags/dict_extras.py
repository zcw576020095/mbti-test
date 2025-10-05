from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """获取字典中的值"""
    if dictionary is None:
        return None
    return dictionary.get(key)

@register.filter
def mul(value, arg):
    """乘法运算"""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def div(value, arg):
    """除法运算"""
    try:
        return int(value) // int(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0