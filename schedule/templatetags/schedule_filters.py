from django import template

register = template.Library()

_RU_DAY_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']


@register.filter
def ru_day_short(value):
    """Short Russian weekday label — Django's |date:"D" is always English
    regardless of LANGUAGE_CODE, so schedule day tabs need this instead."""
    if not value:
        return ''
    return _RU_DAY_SHORT[value.weekday()]
