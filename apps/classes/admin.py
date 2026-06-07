from django.contrib import admin
from .models import Class, Teacher, Sede, Sala, Disciplina, Inscripcion, InscripcionOcurrencia


@admin.register(Sede)
class SedeAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'direccion', 'created_at')
    search_fields = ('nombre',)


@admin.register(Disciplina)
class DisciplinaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion', 'created_at')
    search_fields = ('nombre',)
    
    class PrecioDisciplinaInline(admin.TabularInline):
        from apps.payments.models import PrecioDisciplina
        model = PrecioDisciplina
        extra = 1
        
    inlines = [PrecioDisciplinaInline]


@admin.register(Sala)
class SalaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'capacidad', 'sede', 'created_at')
    search_fields = ('nombre', 'sede__nombre')
    list_filter = ('sede',)


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ('disciplina', 'sala', 'profesor', 'dia_semana', 'hora_inicio', 'duracion', 'cupo_maximo', 'estado')
    list_filter = ('estado', 'dia_semana', 'disciplina', 'sala__sede')
    search_fields = ('disciplina__nombre', 'profesor__nombre', 'profesor__apellido', 'sala__nombre')


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'apellido')
    search_fields = ('nombre', 'apellido')


class InscripcionOcurrenciaInline(admin.TabularInline):
    model = InscripcionOcurrencia
    extra = 0
    fields = ('fecha_clase', 'estado', 'otorga_credito', 'credito')
    readonly_fields = ('credito',)


@admin.register(Inscripcion)
class InscripcionAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'clase', 'periodo', 'tipo', 'estado', 'fecha_inscripcion')
    list_filter = ('estado', 'tipo', 'periodo')
    search_fields = (
        'usuario__username',
        'usuario__dni',
        'usuario__email',
        'clase__disciplina__nombre',
    )
    readonly_fields = ('fecha_inscripcion',)
    inlines = (InscripcionOcurrenciaInline,)


@admin.register(InscripcionOcurrencia)
class InscripcionOcurrenciaAdmin(admin.ModelAdmin):
    list_display = ('inscripcion', 'fecha_clase', 'estado', 'otorga_credito', 'credito')
    list_filter = ('estado', 'otorga_credito')
    search_fields = ('inscripcion__usuario__username', 'inscripcion__usuario__dni')
    date_hierarchy = 'fecha_clase'
