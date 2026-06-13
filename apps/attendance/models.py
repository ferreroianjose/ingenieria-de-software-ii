from django.db import models
from django.conf import settings

class Asistencia(models.Model):
    class Metodo(models.TextChoices):
        QR = "QR", "QR"
        MANUAL = "MANUAL", "Manual"

    inscripcion = models.ForeignKey(
        "classes.Inscripcion",
        on_delete=models.CASCADE,
        related_name="asistencias",
    )
    fecha_hora_ingreso = models.DateTimeField(auto_now_add=True)
    metodo = models.CharField(
        max_length=10,
        choices=Metodo.choices,
        default=Metodo.QR,
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="asistencias_registradas",
    )

    class Meta:
        ordering = ["-fecha_hora_ingreso"]
        verbose_name = "Asistencia"
        verbose_name_plural = "Asistencias"

    def __str__(self):
        return f"Asistencia {self.id} — {self.inscripcion.usuario} ({self.fecha_hora_ingreso:%Y-%m-%d %H:%M})"
