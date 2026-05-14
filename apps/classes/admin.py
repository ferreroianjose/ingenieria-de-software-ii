from django.contrib import admin
from .models import Class, Teacher

@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ('disciplina', 'sala', 'profesor', 'inicio', 'duracion', 'cupo_maximo', 'estado')


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'apellido')
