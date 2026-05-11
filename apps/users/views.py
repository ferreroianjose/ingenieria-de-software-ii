from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import CustomUserCreationForm

# Custom LoginView that forces admins through a 2FA step
class CustomLoginView(LoginView):
    def form_valid(self, form):
        # invocar login y obtener respuesta de redirección estándar
        response = super().form_valid(form)

        # si el usuario es un administrador
        user = self.request.user
        if user.is_staff:
            next_url = (
                response.get("Location")
                if response.has_header("Location")
                else settings.LOGIN_REDIRECT_URL
            )
            self.request.session["is_2fa_pending"] = True
            self.request.session["post_login_next"] = next_url

            return HttpResponseRedirect(reverse("two_factor"))

        return response


@login_required
def two_factor(request):
    user = request.user

    if not user.is_staff:
        return redirect("dashboard")

    if not request.session.get("is_2fa_pending"):
        return redirect("dashboard")

    if request.method == "POST":
        request.session.pop("is_2fa_pending", None)
        next_url = (
            request.session.pop("post_login_next", None) or settings.LOGIN_REDIRECT_URL
        )
        return redirect(next_url)

    next_url = request.session.get("post_login_next", "")
    return render(request, "users/two_factor.html", {"next": next_url})

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
