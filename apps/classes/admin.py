from django.contrib import admin
from .models import Class

@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ('disciplina', 'sala', 'profesor', 'inicio', 'duracion', 'cupo_maximo', 'estado')
