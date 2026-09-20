from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from . import admin_users, admin_groups, admin_schedule, people
from . import email_auth

urlpatterns = [
    path('', views.home, name='home'),
    path('dpo/', views.programs_view, name='programs'),
    path('abiturientu/', views.abiturient_view, name='abiturient'),
    path('login/', views.login_view, name='login'),
    path('register/', email_auth.register, name='register'),
    path('register/verify/', email_auth.verify_email, name='verify_email'),
    path('register/resend/', email_auth.resend_code, name='resend_verification_code'),
    path('register/cancel/', email_auth.cancel_signup, name='cancel_signup'),
    path('password-reset/', email_auth.PortalPasswordResetView.as_view(), name='password_reset'),
    path('password-reset/sent/', auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), name='password_reset_done'),
    path('password-reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html', form_class=email_auth.PortalSetPasswordForm,
    ), name='password_reset_confirm'),
    path('password-changed/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='password_reset_complete'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
    path('profile/', views.profile, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('homework/', views.homework_list, name='homework_list'),
    path('people/', people.people_directory, name='people'),
    path('admin-panel/', admin_users.admin_panel, name='admin_panel'),
    path('admin-panel/users/', admin_users.admin_users, name='admin_users'),
    path('admin-panel/<int:user_id>/edit/', admin_users.admin_edit_user, name='admin_edit_user'),
    path('admin-panel/<int:user_id>/toggle/', admin_users.admin_toggle_user, name='admin_toggle_user'),
    path('admin-panel/groups/', admin_groups.admin_groups, name='admin_groups'),
    path('admin-panel/groups/add/', admin_groups.admin_group_add, name='admin_group_add'),
    path('admin-panel/groups/<int:group_id>/edit/', admin_groups.admin_group_edit, name='admin_group_edit'),
    path('admin-panel/groups/<int:group_id>/delete/', admin_groups.admin_group_delete, name='admin_group_delete'),
    path('admin-panel/schedule/', admin_schedule.admin_schedule, name='admin_schedule'),
    path('admin-panel/schedule/add/', admin_schedule.admin_schedule_create, name='admin_schedule_create'),
    path('admin-panel/schedule/<int:schedule_id>/edit/', admin_schedule.admin_schedule_edit, name='admin_schedule_edit'),
    path('admin-panel/schedule/<int:schedule_id>/delete/', admin_schedule.admin_schedule_delete, name='admin_schedule_delete'),
    path('admin-panel/subjects/', admin_schedule.admin_subjects, name='admin_subjects'),
    path('admin-panel/subjects/add/', admin_schedule.admin_subject_create, name='admin_subject_create'),
    path('admin-panel/subjects/<int:subject_id>/edit/', admin_schedule.admin_subject_edit, name='admin_subject_edit'),
    path('admin-panel/subjects/<int:subject_id>/delete/', admin_schedule.admin_subject_delete, name='admin_subject_delete'),

    # Новости
    path('news/', views.news_list, name='news_list'),
    path('news/add/', views.add_news, name='add_news'),
    path('news/edit/<int:news_id>/', views.edit_news, name='edit_news'),
    path('download/<int:news_id>/', views.download_news, name='download_news'),
    path('news/delete/<int:news_id>/', views.delete_news, name='delete_news'),
]
