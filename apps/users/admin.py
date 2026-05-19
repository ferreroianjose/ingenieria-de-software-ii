from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ("username", "first_name", "last_name", "dni", "rol", "is_staff")
    list_filter = ("rol", "is_staff", "is_superuser", "is_active", "groups")
    fieldsets = UserAdmin.fieldsets + (
        (
            "Información personal",
            {
                "fields": (
                    "dni",
                    "rol",
                    "fecha_nacimiento",
                    "telefono_emergencia",
                    "constancia_tutor",
                    "estado_constancia",
                )
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "dni", "password"),
            },
        ),
    )
    search_fields = ("username", "first_name", "last_name", "dni")

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if "is_staff" not in readonly:
            readonly.append("is_staff")
        return readonly


admin.site.register(User, CustomUserAdmin)
