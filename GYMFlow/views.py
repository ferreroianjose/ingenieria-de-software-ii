from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required

# primera pagina que accede el usuario
def root(request):
    # verificar si existe una sesión cacheada válida y redirigir al panel
    # sino redirigir a la pantalla de login
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("login")


@login_required
def dashboard(request):
    """Página principal después de iniciar sesión."""
    user = request.user

    if user.rol == "ADMIN":
        return render(request, "dashboards/admin.html")

    if user.rol == "EMPLEADO":
        return render(request, "dashboards/empleado.html")

    # Mockup only — not loaded from the DB until client subscriptions exist.
    return render(
        request,
        "dashboards/cliente.html",
        {
            "yoga_sessions": [
                {"day": "Lunes", "time": "08:00"},
                {"day": "Jueves", "time": "18:30"},
            ],
            "pilates_sessions": [
                {"day": "Miércoles", "time": "17:30"},
                {"day": "Viernes", "time": "17:30"},
            ],
        },
    )
