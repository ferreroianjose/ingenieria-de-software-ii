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

    disciplina = models.ForeignKey(Disciplina, on_delete=models.CASCADE, null=True, blank=True)
    sala = models.ForeignKey(Sala, on_delete=models.CASCADE, null=True, blank=True)
    profesor = models.ForeignKey('Teacher', on_delete=models.CASCADE)
    inicio = models.DateTimeField()
    duracion = models.DurationField()
    cupo_maximo = models.PositiveIntegerField(default=1)
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='disponible'
    )

    def __str__(self):
        return f"{self.disciplina} - {self.profesor} - {self.inicio}"

    @property
    def duracion_minutos(self):
        return int(self.duracion.total_seconds() // 60)

