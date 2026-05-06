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
    return render(request, "dashboard.html")
