from django.contrib import admin
from .models import Class, Teacher, Sede, Sala, Disciplina


@admin.register(Sede)
class SedeAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'direccion', 'created_at')
    search_fields = ('nombre',)


@admin.register(Disciplina)
class DisciplinaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion', 'created_at')
    search_fields = ('nombre',)


@admin.register(Sala)
class SalaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'capacidad', 'sede', 'created_at')
    search_fields = ('nombre', 'sede__nombre')
    list_filter = ('sede',)


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ('disciplina', 'sala', 'profesor', 'inicio', 'duracion', 'cupo_maximo', 'estado')


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'apellido')
