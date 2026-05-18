# users/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    # Redirigir /users/ -> /users/login/
    path('', RedirectView.as_view(pattern_name='login', permanent=False)),

    path('login/', views.CustomLoginView.as_view(
        template_name='users/login.html',
        redirect_authenticated_user=True,
    ), name='login'),

    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('register/', views.register, name='register'),

    path('2fa/', views.two_factor, name='two_factor'),

    path('settings/', views.settings_view, name='settings'),

    path('manage/', views.staff_clientes, name='manage'),

    # TODO: agregar password reset, etc.

    # Gestión de usuarios (solo admin)
    path('gestion/', views.user_list, name='user_list'),
    path('gestion/<int:user_id>/cambiar-rol/', views.change_user_role, name='change_user_role'),
    path('gestion/<int:user_id>/eliminar/', views.delete_user, name='delete_user'),
]
