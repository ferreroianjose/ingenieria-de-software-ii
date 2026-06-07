from django.db import models
from django.conf import settings
from apps.classes.models import Disciplina

class PeriodoCobro(models.Model):
    nombre = models.CharField(max_length=100)
    fecha_inicio_periodo = models.DateField()
    fecha_fin_periodo = models.DateField()
    apertura_abonados = models.DateField()
    apertura_general = models.DateField()

    def __str__(self):
        return self.nombre

class PrecioClase(models.Model):
    clase = models.ForeignKey('classes.Class', on_delete=models.CASCADE)
    periodo = models.ForeignKey(PeriodoCobro, on_delete=models.CASCADE)
    monto = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('clase', 'periodo')

    def __str__(self):
        return f"{self.clase} - {self.periodo}: ${self.monto}"

class Pago(models.Model):
    class Metodo(models.TextChoices):
        EFECTIVO = 'EFECTIVO', 'Efectivo'
        MERCADOPAGO = 'MERCADOPAGO', 'MercadoPago'
        CREDITO = 'CREDITO', 'Crédito'

    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        COMPLETADO = 'COMPLETADO', 'Completado'
        FALLIDO = 'FALLIDO', 'Fallido'
        REEMBOLSADO = 'REEMBOLSADO', 'Reembolsado'

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    periodo = models.ForeignKey(PeriodoCobro, on_delete=models.PROTECT)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_pago = models.DateTimeField(auto_now_add=True)
    metodo = models.CharField(max_length=20, choices=Metodo.choices)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)

    def __str__(self):
        return f"Pago {self.id} - {self.usuario} - ${self.monto}"

class PagoInscripcion(models.Model):
    pago = models.ForeignKey(Pago, on_delete=models.CASCADE, related_name='detalles')
    inscripcion = models.ForeignKey('classes.Inscripcion', on_delete=models.PROTECT)
    monto_aplicado = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Detalle Pago {self.pago.id} - Inscripcion {self.inscripcion.id}"

class Credito(models.Model):
    class Estado(models.TextChoices):
        DISPONIBLE = 'DISPONIBLE', 'Disponible'
        UTILIZADO = 'UTILIZADO', 'Utilizado'

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    periodo = models.ForeignKey(PeriodoCobro, on_delete=models.CASCADE)
    disciplina = models.ForeignKey(Disciplina, on_delete=models.CASCADE)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.DISPONIBLE)

    def __str__(self):
        return f"Credito {self.usuario} - {self.disciplina} ({self.estado})"
