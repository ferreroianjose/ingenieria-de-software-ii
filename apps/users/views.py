import random
import string
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator

from apps.notifications.services import notification_service
from GYMFlow.access import admin_required, staff_required
from GYMFlow.page_chrome import PAGE_CHROME_LIGHT, merge_page_chrome
from .forms import (
    CustomUserCreationForm,
    GymAuthenticationForm,
    ProfileUpdateForm,
    TwoFactorForm,
)
from .search import USER_PAGE_SIZE, filter_users_queryset

User = get_user_model()


@login_required
def settings_view(request):
    context = {
        **merge_page_chrome(PAGE_CHROME_LIGHT),
        "profile_form": ProfileUpdateForm(instance=request.user),
    }
    if request.user.rol == "ADMIN":
        context["adapters"] = notification_service.adapters
    return render(request, "users/settings.html", context)


@login_required
def update_profile(request):
    if request.method == "POST":
        form = ProfileUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Teléfono de emergencia actualizado.")
        else:
            messages.error(request, "Error al actualizar el teléfono de emergencia.")
    return redirect("settings")


# Custom LoginView that forces admins through a 2FA step
class CustomLoginView(LoginView):
    form_class = GymAuthenticationForm

    def form_valid(self, form):
        response = super().form_valid(form)

        user = self.request.user
        if user.rol == "ADMIN":
            code = "".join(random.choices(string.digits, k=6))

            notification_service.notify(
                recipient=user,
                subject="Tu código de seguridad GYMFlow",
                message=f"Hola {user.first_name}, tu código de verificación es: {code}. No compartas este código con nadie.",
                template_name="two_factor",
                context={"user": user, "code": code},
            )

            next_url = (
                response.get("Location")
                if response.has_header("Location")
                else settings.LOGIN_REDIRECT_URL
            )

            self.request.session["is_2fa_pending"] = True
            self.request.session["2fa_code"] = code
            self.request.session["post_login_next"] = next_url

            return HttpResponseRedirect(reverse("two_factor"))

        return response


@login_required
def two_factor(request):
    user = request.user

    if not user.rol == "ADMIN":
        return redirect("dashboard")

    if not request.session.get("is_2fa_pending"):
        return redirect("dashboard")

    expected_code = request.session.get("2fa_code")

    if request.method == "POST":
        form = TwoFactorForm(request.POST, expected_code=expected_code)
        if form.is_valid():
            request.session.pop("is_2fa_pending", None)
            request.session.pop("2fa_code", None)
            next_url = (
                request.session.pop("post_login_next", None)
                or settings.LOGIN_REDIRECT_URL
            )
            return redirect(next_url)
    else:
        form = TwoFactorForm(expected_code=expected_code)

    next_url = request.session.get("post_login_next", "")
    return render(
        request,
        "users/two_factor.html",
        {
            "form": form,
            "next": next_url,
        },
    )


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect("dashboard")
    else:
        form = CustomUserCreationForm()

    return render(
        request,
        "users/register.html",
        {
            "form": form,
            "password_help_texts": "La contraseña debe tener 10 o más caracteres, incluyendo letras, números y al menos un carácter especial.",
        },
    )


@staff_required
def _staff_users_queryset(request):
    qs = User.objects.order_by("last_name", "first_name", "email")
    # Si es empleado solo puede ver clientes
    if request.user.rol == "EMPLEADO":
        qs = qs.filter(rol="CLIENTE")
    return qs


@staff_required
def get_staff_user(request, user_id):
    user = get_object_or_404(_staff_users_queryset(request), pk=user_id)
    return user


@staff_required
def _user_rows_context(request):
    q = (request.GET.get("q") or "").strip()
    qs = filter_users_queryset(_staff_users_queryset(request), q)
    page_obj = Paginator(qs, USER_PAGE_SIZE).get_page(request.GET.get("page") or 1)
    is_admin = request.user.rol == "ADMIN"
    return {
        "searched": True,
        "q": q,
        "page_obj": page_obj,
        "can_manage": is_admin,
        "empty_search_message": (
            "Presioná «Buscar» para listar usuarios."
            if is_admin
            else "Presioná «Buscar» para listar clientes."
        ),
    }


def _user_drawer_context(request, user, *, role_updated=False):
    return {
        "user": user,
        "can_manage": request.user.rol == "ADMIN",
        "roles": User.ROLES,
        "role_updated": role_updated,
    }


@staff_required
def staff_clientes(request):
    is_admin = request.user.rol == "ADMIN"
    return render(
        request,
        "users/manage.html",
        {
            "can_manage": is_admin,
            "page_title": "Usuarios" if is_admin else "Clientes",
            "page_subtitle": (
                "Buscá usuarios, abrí la ficha, modificá sus roles o eliminalos."
                if is_admin
                else "Buscá clientes y abrí la ficha para ver sus datos y modificar su estado de constancia (#TODO)."
            ),
            "search_placeholder": ("Nombre, email o DNI…"),
            "empty_search_message": (
                "Presioná «Buscar» para listar usuarios."
                if is_admin
                else "Presioná «Buscar» para listar clientes."
            ),
        },
    )


@staff_required
def user_rows(request):
    return render(request, "users/_user_table_panel.html", _user_rows_context(request))


@staff_required
def user_detail_drawer(request, user_id):
    user = get_staff_user(request, user_id)
    return render(
        request,
        "users/_user_detail_drawer_panel.html",
        _user_drawer_context(request, user),
    )


@admin_required
def change_user_role(request, user_id):
    user = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        new_role = request.POST.get("rol")
        if new_role and new_role in dict(User.ROLES):
            user.rol = new_role
            user.save()

        if request.headers.get("HX-Request"):
            return render(
                request,
                "users/_user_detail_drawer_panel.html",
                _user_drawer_context(request, user, role_updated=True),
            )

        return redirect("manage")

    return redirect("manage")


@admin_required
def delete_user(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    if request.method == "POST":
        user.delete()
        return redirect("manage")
    return render(request, "users/delete_user.html", {"user": user})
