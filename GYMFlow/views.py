from django.shortcuts import redirect

# primera pagina que accede el usuario
def root(request):
    # verificar si existe una sesión cacheada válida y redirigir al panel
    # sino redirigir a la pantalla de login
    # por ahora siempre redirigir a la pantalla de login
    return redirect("login")
