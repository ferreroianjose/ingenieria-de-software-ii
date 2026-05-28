from django.conf import settings
from django.db import models


class Sede(models.Model):
    """Modelo para sedes/ubicaciones del gimnasio"""
    nombre = models.CharField(max_length=100, unique=True)
    direccion = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'sedes'

    def __str__(self):
        return self.nombre


class Disciplina(models.Model):
    """Modelo para disciplinas/tipos de clases"""
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'disciplinas'

    def __str__(self):
        return self.nombre


class Sala(models.Model):
    """Modelo para salas de clases"""
    nombre = models.CharField(max_length=100)
    capacidad = models.PositiveIntegerField()
    sede = models.ForeignKey(Sede, on_delete=models.CASCADE, related_name='salas')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('nombre', 'sede')
        verbose_name_plural = 'salas'

    def __str__(self):
        return f"{self.nombre} - {self.sede.nombre}"


class Teacher(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)

    class Meta:
        unique_together = ('nombre', 'apellido')

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class Class(models.Model):
    ESTADO_CHOICES = [
        ('disponible', 'Disponible'),
        ('pausada', 'Pausada'),
    ]

    WEEKDAY_CHOICES = [
        (0, 'Lunes'),
        (1, 'Martes'),
        (2, 'Miércoles'),
        (3, 'Jueves'),
        (4, 'Viernes'),
        (5, 'Sábado'),
        (6, 'Domingo'),
    ]

    disciplina = models.ForeignKey(Disciplina, on_delete=models.PROTECT, null=True, blank=True)
    sala = models.ForeignKey(Sala, on_delete=models.PROTECT, null=True, blank=True)
    profesor = models.ForeignKey('Teacher', on_delete=models.PROTECT)
    dia_semana = models.PositiveSmallIntegerField(choices=WEEKDAY_CHOICES, default=0)
    hora_inicio = models.TimeField(null=True, blank=True)
    duracion = models.DurationField()
    cupo_maximo = models.PositiveIntegerField(default=1)
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='disponible'
    )

    def __str__(self):
        return f"{self.disciplina} - {self.profesor} - {self.get_dia_semana_display()} {self.hora_inicio}"

    @property
    def duracion_minutos(self):
        return int(self.duracion.total_seconds() // 60)


class Inscripcion(models.Model):
    class Estado(models.TextChoices):
        ESPERA = "ESPERA", "En lista de espera"
        RESERVADA = "RESERVADA", "Reservada"
        PENDIENTE_PAGO = "PENDIENTE_PAGO", "Pendiente de pago"
        CANCELADA = "CANCELADA", "Cancelada"

    class Tipo(models.TextChoices):
        MENSUAL = "MENSUAL", "Abonado (mensual)"
        CLASE_SUELTA = "CLASE_SUELTA", "No Abonado (clase suelta)"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="inscripciones",
    )
    clase = models.ForeignKey(
        Class,
        on_delete=models.CASCADE,
        related_name="inscripciones",
    )
    periodo = models.ForeignKey(
        'payments.PeriodoCobro',
        on_delete=models.PROTECT,
        related_name="inscripciones",
        null=True, #TODO: ELIMINAR LUEGO! reason: migraciones.
    )
    tipo = models.CharField(
        max_length=20,
        choices=Tipo.choices,
        default=Tipo.CLASE_SUELTA,
    )
    fecha_inscripcion = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.RESERVADA,
    )

    class Meta:
        ordering = ["fecha_inscripcion"]

    def __str__(self):
        return f"{self.usuario} — {self.clase} ({self.get_estado_display()})"
