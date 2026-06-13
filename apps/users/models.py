from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLES = (
        ("CLIENTE", "Cliente"),
        ("EMPLEADO", "Empleado"),
        ("ADMIN", "Administrador"),
    )
    ESTADOS = (
        ("PENDIENTE", "Pendiente"),
        ("APROBADA", "Aprobada"),
        ("RECHAZADA", "Rechazada"),
    )

    email = models.EmailField(unique=True)  # Override para unicidad
    rol = models.CharField(max_length=20, choices=ROLES, default="CLIENTE")
    dni = models.CharField(max_length=20, unique=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    telefono_emergencia = models.CharField(max_length=20, blank=True)
    estado_constancia = models.CharField(
        max_length=20, choices=ESTADOS, default="PENDIENTE"
    )

    REQUIRED_FIELDS = ["dni", "first_name", "last_name", "email"]

    # Django define email y username como parte del usuario por defecto
    # para evitar sobreescribir métodos y otros problemas,
    # manejamos username = email.
    def save(self, *args, **kwargs):
        self.username = self.email
        if self.is_superuser:
            self.rol = "ADMIN"
        # is_staff controla solo el Django Admin (/admin/), no el panel de la app.
        self.is_staff = self.rol == "ADMIN"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"

    def get_notification_contact(self, channel_slug: str) -> str:
        """
        Retorna el dato de contacto (email, teléfono, etc.) según el canal solicitado.
        """
        mapping = {
            "email": self.email,
            "fake_email": self.email,
            # "sms": self.telefono_emergencia,
        }
        return mapping.get(channel_slug, "")
