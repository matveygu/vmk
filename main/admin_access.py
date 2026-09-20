"""Access policy shared by the portal's administration screens."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def admin_required(view):
    @login_required
    @wraps(view)
    def guarded(request, *args, **kwargs):
        if not request.user.is_active or request.user.role != 'admin':
            raise PermissionDenied('Раздел доступен только администраторам портала.')
        return view(request, *args, **kwargs)
    return guarded


def role_required(test_func, message='Недостаточно прав для доступа к этому разделу.'):
    """Like @user_passes_test, but a logged-in user who fails the check gets a 403
    page instead of being silently bounced back to the login screen they're already past."""
    def decorator(view):
        @login_required
        @wraps(view)
        def guarded(request, *args, **kwargs):
            if not request.user.is_active or not test_func(request.user):
                raise PermissionDenied(message)
            return view(request, *args, **kwargs)
        return guarded
    return decorator
