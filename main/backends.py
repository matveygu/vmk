from django.contrib.auth.backends import ModelBackend
from .models import CustomUser


class StudentIDBackend(ModelBackend):
    """Custom authentication backend that uses student_id instead of username"""
    
    def authenticate(self, request, student_id=None, password=None, **kwargs):
        student_id = student_id or kwargs.get('username')
        if not student_id or password is None:
            return None
        try:
            user = CustomUser.objects.get(student_id=student_id)
        except CustomUser.DoesNotExist:
            CustomUser().set_password(password)
            return None
        
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
    
    def get_user(self, user_id):
        try:
            user = CustomUser.objects.get(pk=user_id)
            return user if self.user_can_authenticate(user) else None
        except CustomUser.DoesNotExist:
            return None
