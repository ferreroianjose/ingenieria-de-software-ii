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
    constancia_tutor = models.FileField(upload_to="constancias/", null=True, blank=True)
    estado_constancia = models.CharField(
        max_length=20, choices=ESTADOS, default="PENDIENTE"
    )

    # Django define email y username como parte del usuario por defecto
    # para evitar sobreescribir métodos y otros problemas,
    # manejamos username = email.
    def save(self, *args, **kwargs):
        self.username = self.email
        if self.is_superuser:
            self.rol = "ADMIN"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"
