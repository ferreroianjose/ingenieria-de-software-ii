import random
import string
from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.template.loader import render_to_string
from django.middleware.csrf import get_token

from apps.notifications.services import notification_service
from GYMFlow.access import staff_required
from .forms import CustomUserCreationForm, TwoFactorForm

@login_required
def settings_view(request):
    # Contexto para el partial de notificaciones (si el usuario tiene permisos)
    context = {}
    if request.user.rol == "ADMIN":
        context["adapters"] = notification_service.adapters
        
    return render(request, "users/settings.html", context)


# Custom LoginView that forces admins through a 2FA step
class CustomLoginView(LoginView):
    def form_valid(self, form):
        # invocar login y obtener respuesta de redirección estándar
        response = super().form_valid(form)

        # si el usuario es un administrador
        user = self.request.user
        if user.rol == "ADMIN":
            # Generar código de 6 dígitos
            code = "".join(random.choices(string.digits, k=6))

            # Enviar notificación
            notification_service.notify(
                recipient=user,
                subject="Tu código de seguridad GYMFlow",
                message=f"Hola {user.first_name}, tu código de verificación es: {code}. No compartas este código con nadie.",
                template_name="two_factor",
                context={"user": user, "code": code}
            )

            next_url = (
                response.get("Location")
                if response.has_header("Location")
                else settings.LOGIN_REDIRECT_URL
            )
            
            # Guardar en sesión
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
                request.session.pop("post_login_next", None) or settings.LOGIN_REDIRECT_URL
            )
            return redirect(next_url)
    else:
        form = TwoFactorForm(expected_code=expected_code)

    next_url = request.session.get("post_login_next", "")
    return render(request, "users/two_factor.html", {
        "form": form,
        "next": next_url
    })

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

    return render(request, "users/register.html", {
        "form": form,
        "password_help_texts": "La contraseña debe tener 10 o más caracteres, incluyendo letras, números y al menos un carácter especial."
    })

@staff_required
def staff_clientes(request):
    return render(request, "users/manage.html")

# --- Gestión de usuarios (solo admin) ---

User = get_user_model()

def admin_required(view_func):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff)(view_func)

@admin_required
def user_list(request):
    users = User.objects.all()
    roles_choices = getattr(User, 'ROLES', [])
    # Pasamos 'roles' para que el archivo partial pueda renderizar las opciones la primera vez
    return render(request, "users/user_list.html", {"users": users, "roles": roles_choices})

@admin_required
def change_user_role(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    roles_choices = getattr(User, 'ROLES', [])

    if request.method == "POST":
        new_role = request.POST.get("rol")
        if new_role and new_role in dict(roles_choices):
            user.rol = new_role
            user.save()

            # SI LA PETICIÓN VIENE DE HTMX: Devolvemos únicamente el partial de la celda
            if request.headers.get('HX-Request'):
                context = {
                    'user': user, 
                    'roles': roles_choices, 
                    'csrf_token': get_token(request) # Forzamos la regeneración segura del token para HTMX
                }
                html = render_to_string('users/user_role_cell.html', context, request=request)
                return HttpResponse(html)

            return redirect("user_list")

    return redirect("user_list")

@admin_required
def delete_user(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    if request.method == "POST":
        user.delete()
        return redirect("user_list")
    return render(request, "users/delete_user.html", {"user": user})
