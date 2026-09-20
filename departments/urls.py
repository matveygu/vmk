from django.urls import path
from . import views

urlpatterns = [
    path('', views.department_list, name='department_list'),
    path('<slug:dept_id>/', views.department_detail, name='department_detail'),
]
