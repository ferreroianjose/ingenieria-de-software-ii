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
from apps.core.access import admin_required, staff_required
from apps.core.page_chrome import PAGE_CHROME_LIGHT, merge_page_chrome
from .forms import (
    CustomUserCreationForm,
    GymAuthenticationForm,
    ProfileUpdateForm,
    TwoFactorForm,
    UserAdminUpdateForm,
    InternalUserCreationForm,
)
from .search import USER_PAGE_SIZE, filter_users_queryset
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.template.loader import render_to_string

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
            error_msg = "Error al actualizar el teléfono de emergencia."
            if form.errors:
                error_msg = list(form.errors.values())[0][0]
            messages.error(request, error_msg)
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
def create_internal_user(request):
    if request.method == "POST":
        form = InternalUserCreationForm(request.POST, creator=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_unusable_password()
            user.save()

            context = {
                "email": user.email,
                "domain": request.META.get("HTTP_HOST", "localhost:8000"),
                "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                "user": user,
                "token": default_token_generator.make_token(user),
                "protocol": "https" if request.is_secure() else "http",
            }
            subject = "Configura tu contraseña para GYMFlow"
            body = render_to_string("users/password_setup_email.html", context)

            notification_service.notify(
                recipient=user,
                subject=subject,
                message=body,
                html_message=render_to_string(
                    "users/password_setup_email_html.html", context
                ),
            )

            msg = f"Usuario {user.get_full_name()} creado. Se ha enviado un correo para que establezca su contraseña."
            if request.headers.get("HX-Request"):
                return hx_ok(
                    request,
                    message=msg,
                    close_modal="userDrawerOpen",
                    refresh={
                        "url": reverse("user_rows"),
                        "target": "#users-table-panel",
                    },
                )
            messages.success(request, msg)
            return redirect("manage")
        else:
            if request.headers.get("HX-Request"):
                user_type = "Usuario" if request.user.rol == "ADMIN" else "Cliente"
                return render(
                    request,
                    "users/_create_user_drawer_panel.html",
                    {
                        "form": form,
                        "modal_title": f"Crear {user_type}",
                        "modal_subtitle": f"Completa los datos para dar de alta al nuevo {user_type.lower()}. Se enviará un correo para configurar la contraseña.",
                        "modal_button_label": f"Crear {user_type.lower()}",
                    },
                )
    else:
        form = InternalUserCreationForm(creator=request.user)

    if request.headers.get("HX-Request"):
        user_type = "Usuario" if request.user.rol == "ADMIN" else "Cliente"
        return render(
            request,
            "users/_create_user_drawer_panel.html",
            {
                "form": form,
                "modal_title": f"Crear {user_type}",
                "modal_subtitle": f"Completa los datos para dar de alta al nuevo {user_type.lower()}. Se enviará un correo para configurar la contraseña.",
                "modal_button_label": f"Crear {user_type.lower()}",
            },
        )

    return render(
        request,
        "users/create_internal_user.html",
        {
            "form": form,
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
    is_admin = request.user.rol == "ADMIN"
    is_empleado = request.user.rol == "EMPLEADO"
    can_manage = is_admin or (is_empleado and user.rol == "CLIENTE")
    return {
        "user": user,
        "can_manage": can_manage,
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
                "Buscá usuarios, seleccionalos para editar su ficha, modificar sus roles o eliminarlos."
                if is_admin
                else "Buscá clientes y seleccionalos para ver sus datos y modificar su estado de constancia."
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


@staff_required
def update_user_admin(request, user_id):
    user = get_staff_user(request, user_id)
    is_admin = request.user.rol == "ADMIN"

    if request.method == "POST":
        original_role = user.rol
        form = UserAdminUpdateForm(request.POST, instance=user)

        if form.is_valid():
            # Security check: Only admins can change the role
            if not is_admin and form.cleaned_data.get("rol") != original_role:
                form.instance.rol = original_role

            form.save()

            if request.headers.get("HX-Request"):
                return render(
                    request,
                    "users/_user_detail_drawer_panel.html",
                    _user_drawer_context(request, user, role_updated=True),
                )
            return redirect("manage")
        else:
            # If form has errors, we re-render the drawer with errors
            context = _user_drawer_context(request, user)
            context["form"] = form
            if request.headers.get("HX-Request"):
                return render(
                    request,
                    "users/_user_detail_drawer_panel.html",
                    context,
                )
            return redirect("manage")

    return redirect("manage")


from django.db.models import ProtectedError
from apps.classes.htmx import hx_ok


@admin_required
def delete_user(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    if request.method == "POST":
        try:
            nombre = user.get_full_name()
            user.delete()
            messages.success(request, f"El usuario {nombre} ha sido eliminado.")
            if request.headers.get("HX-Request"):
                return hx_ok(
                    request,
                    message=f"El usuario {nombre} ha sido eliminado.",
                    refresh={
                        "url": reverse("user_rows"),
                        "target": "#users-table-panel",
                    },
                )
            return redirect("manage")
        except ProtectedError:
            if request.headers.get("HX-Request"):
                return hx_ok(
                    request,
                    message="No se puede eliminar el usuario porque tiene historial en el sistema (pagos, inscripciones, etc).",
                    level="error",
                )
            messages.error(
                request,
                "No se puede eliminar el usuario porque tiene historial en el sistema.",
            )
            return redirect("manage")
    return render(request, "users/delete_user.html", {"user": user})
