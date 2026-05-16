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
    context = {
        'yoga_sessions': [
            {'day': 'Lunes', 'time': '08:00'},
        ],
        'pilates_sessions': [
            {'day': 'Miércoles', 'time': '17:30'},
            {'day': 'Viernes', 'time': '17:30'},
        ],
    }

    if user.rol == "ADMIN":
        template_name = "dashboards/admin.html"
    
    elif user.rol == "EMPLEADO":
        template_name = "dashboards/empleado.html"
    
    else:  # CLIENTE
        template_name = "dashboards/cliente.html"

    return render(request, template_name, context)
