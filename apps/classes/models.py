from django.db import models

class Class(models.Model):
    DISCIPLINA_CHOICES = [
        ('Funcional', 'Funcional'),
        ('Pilates', 'Pilates'),
        ('Yoga', 'Yoga'),
    ]
    SALA_CHOICES = [
        ('A', 'A'),
        ('B', 'B'),
    ]
    ESTADO_CHOICES = [
        ('disponible', 'Disponible'),
        ('pausada', 'Pausada'),
    ]

    disciplina = models.CharField(max_length=100, choices=DISCIPLINA_CHOICES)
    sala = models.CharField(max_length=100, choices=SALA_CHOICES)
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


class Teacher(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)

    class Meta:
        unique_together = ('nombre', 'apellido')

    def __str__(self):
        return f"{self.nombre} {self.apellido}"

