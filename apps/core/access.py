from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect


def role_required(*roles):
    """Require an authenticated user whose `rol` is one of `roles`."""

    allowed = frozenset(roles)

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            user = request.user

            if not user.is_authenticated:
                return redirect_to_login(request.get_full_path())

            if user.rol not in allowed:
                messages.error(
                    request,
                    "No tenés permiso para acceder a esta sección.",
                )
                return redirect("dashboard")
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


admin_required = role_required("ADMIN")
empleado_required = role_required("EMPLEADO")
staff_required = role_required("ADMIN", "EMPLEADO")
