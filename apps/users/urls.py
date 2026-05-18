# users/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="login", permanent=False)),

    path(
        "login/",
        views.CustomLoginView.as_view(
            template_name="users/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),

    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    path("register/", views.register, name="register"),

    path("2fa/", views.two_factor, name="two_factor"),

    path("settings/", views.settings_view, name="settings"),

    path("manage/", views.staff_clientes, name="manage"),
    path("manage/rows/", views.user_rows, name="user_rows"),
    path("manage/<int:user_id>/drawer/", views.user_detail_drawer, name="user_detail_drawer"),
    path("manage/<int:user_id>/cambiar-rol/", views.change_user_role, name="change_user_role"),
    path("manage/<int:user_id>/eliminar/", views.delete_user, name="delete_user"),

    path(
        "settings/rows/",
        RedirectView.as_view(pattern_name="user_rows", permanent=False),
    ),
]
