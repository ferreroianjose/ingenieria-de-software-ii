# users/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from . import views
from .forms import CustomPasswordResetForm

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

    path(
        "password_reset/",
        auth_views.PasswordResetView.as_view(
            template_name="users/password_reset_form.html",
            form_class=CustomPasswordResetForm,
            email_template_name="users/password_reset_email.html",
            html_email_template_name="users/password_reset_email_html.html",
            subject_template_name="users/password_reset_subject.txt",
        ),
        name="password_reset",
    ),
    path(
        "password_reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="users/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="users/password_reset_confirm.html",
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="users/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),

    path("register/", views.register, name="register"),

    path("2fa/", views.two_factor, name="two_factor"),

    path("settings/", views.settings_view, name="settings"),
    path("settings/profile/", views.update_profile, name="update_profile"),

    path("manage/", views.staff_clientes, name="manage"),
    path("manage/rows/", views.user_rows, name="user_rows"),
    path("manage/crear/", views.create_internal_user, name="create_internal_user"),
    path("manage/<int:user_id>/drawer/", views.user_detail_drawer, name="user_detail_drawer"),
    path("manage/<int:user_id>/editar/", views.update_user_admin, name="update_user_admin"),
    path("manage/<int:user_id>/eliminar/", views.delete_user, name="delete_user"),

    path(
        "settings/rows/",
        RedirectView.as_view(pattern_name="user_rows", permanent=False),
    ),
]
