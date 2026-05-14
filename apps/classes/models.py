from django.db import models

class Class(models.Model):
    disciplina = models.CharField(max_length=100)
    sala = models.CharField(max_length=100)
    profesor = models.CharField(max_length=100)
    inicio = models.DateTimeField()
    duracion = models.DurationField()  # Duración en formato de tiempo
    cupo = models.IntegerField()
    estado = models.CharField(
        max_length=20,
        choices=[('disponible', 'Disponible'), ('pausada', 'Pausada')],
        default='disponible'
    )

    def __str__(self):
        return f"{self.disciplina} - {self.profesor} - {self.inicio}"
