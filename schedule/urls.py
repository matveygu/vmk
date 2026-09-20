from django.urls import path
from . import views
from django.views.generic import RedirectView

urlpatterns = [
    path('public/', views.public_schedule_view, name='public_schedule'),
    path('', views.schedule_view, name='schedule'),
    path('add-homework/<int:schedule_id>/', views.add_homework, name='add_homework'),
    path('download-homework/<int:schedule_id>/', views.download_homework_file, name='download_homework_file'),
    path('api/schedule/', views.schedule_json, name='schedule_json'),
    path('api/schedule/<str:day>/', views.schedule_json, name='schedule_json_day'),
    # <int:schedule_id>/ must come before <str:day>/ — otherwise numeric IDs are
    # swallowed by the legacy day-name route and schedule_detail is unreachable.
    path('<int:schedule_id>/', views.schedule_detail, name='schedule_detail'),
    path('<int:schedule_id>/add_homework/', views.add_homework, name='add_homework'),
    path('delete_homework/<int:schedule_id>/', views.delete_homework, name='delete_homework'),
    path('<str:day>/', views.day_schedule, name='day_schedule'),  # Для обратной совместимости
]