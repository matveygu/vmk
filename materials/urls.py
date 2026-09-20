from django.urls import path
from . import views

urlpatterns = [
    # Drive-style browsing
    path('drive/', views.drive_root, name='materials_drive_root'),
    path('drive/<int:folder_id>/', views.drive_folder, name='materials_drive_folder'),

    # Главная страница материалов
    path('', views.materials_view, name='materials'),

    # Материалы по типу
    path('<str:faculty>/<int:course>/<str:subject>/<str:material_type>/',
         views.legacy_materials_redirect, name='type_materials'),

    # Загрузка материала
    path('upload/', views.upload_material, name='upload_material'),

    # Редактирование материала
    path('edit/<int:material_id>/', views.edit_material, name='edit_material'),

    # Создание папки
    path('create-folder/', views.create_folder, name='create_material_folder'),
    path('create-folder/<int:parent_id>/', views.create_folder, name='create_material_subfolder'),

    # Скачивание материала
    path('download/<int:material_id>/', views.download_material, name='download_material'),

    # Просмотр материала (видео и другое)
    path('view/<int:material_id>/', views.view_material, name='view_material'),

    # Удаление материала
    path('delete/<int:material_id>/', views.delete_material, name='delete_material'),

    # Операции с папками
    path('folder/<int:folder_id>/edit/', views.edit_folder, name='edit_material_folder'),
    path('folder/<int:folder_id>/rename/', views.rename_folder, name='rename_material_folder'),
    path('folder/<int:folder_id>/delete/', views.delete_folder, name='delete_material_folder'),

    # Материалы по факультету
    path('<str:faculty>/', views.legacy_materials_redirect, name='faculty_materials'),

    # Материалы по курсу
    path('<str:faculty>/<int:course>/', views.legacy_materials_redirect, name='course_materials'),

    # Материалы по предмету
    path('<str:faculty>/<int:course>/<str:subject>/', views.legacy_materials_redirect, name='subject_materials'),

]