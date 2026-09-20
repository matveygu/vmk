from django import template

register = template.Library()


@register.filter(name='has_role')
def has_role(user, roles_str):
    """Return True if user.role is one of the roles in the comma-separated string.

    Usage: {% if user|has_role:"admin,teacher" %}
    """
    if not hasattr(user, 'role'):
        return False
    roles = [r.strip() for r in roles_str.split(',')]
    return user.role in roles
