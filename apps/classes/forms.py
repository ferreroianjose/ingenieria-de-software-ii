from datetime import timedelta, datetime, time

from django import forms
from django.core.exceptions import ValidationError

from .models import Class, Teacher, Sede, Sala, Disciplina


class SedeForm(forms.ModelForm):
    class Meta:
        model = Sede
        fields = ['nombre', 'direccion']
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Nombre de la sede'}),
            'direccion': forms.TextInput(attrs={'placeholder': 'Dirección'}),
        }


class DisciplinaForm(forms.ModelForm):
    class Meta:
        model = Disciplina
        fields = ['nombre', 'descripcion']
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Nombre de la disciplina'}),
            'descripcion': forms.Textarea(attrs={'placeholder': 'Descripción', 'rows': 3}),
        }


class SalaForm(forms.ModelForm):
    sede = forms.ModelChoiceField(
        queryset=Sede.objects.all(),
        label='Sede',
        empty_label='Selecciona una sede'
    )

    class Meta:
        model = Sala
        fields = ['nombre', 'capacidad', 'sede']
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Nombre de la sala'}),
            'capacidad': forms.NumberInput(attrs={'placeholder': 'Capacidad máxima', 'min': 1}),
        }


class ClassForm(forms.ModelForm):
    WEEKDAY_CHOICES = [
        (0, 'Lunes'),
        (1, 'Martes'),
        (2, 'Miércoles'),
        (3, 'Jueves'),
        (4, 'Viernes'),
    ]

    sede = forms.ModelChoiceField(
        queryset=Sede.objects.all(),
        label='Sede',
        empty_label='Selecciona una sede'
    )

    disciplina = forms.ModelChoiceField(
        queryset=Disciplina.objects.all(),
        label='Disciplina',
        empty_label='Selecciona una disciplina'
    )

    sala = forms.ModelChoiceField(
        queryset=Sala.objects.all(),
        label='Sala',
        empty_label='Selecciona una sala'
    )

    profesor = forms.ModelChoiceField(
        queryset=Teacher.objects.all(),
        label='Profesor',
        empty_label='Selecciona un profesor'
    )

    dia_semana = forms.ChoiceField(
        choices=WEEKDAY_CHOICES,
        label='Día de la semana'
    )

    hora = forms.IntegerField(
        min_value=0,
        max_value=23,
        label='Hora',
        widget=forms.NumberInput(attrs={'placeholder': 'HH'})
    )

    minuto = forms.IntegerField(
        min_value=0,
        max_value=59,
        label='Minuto',
        widget=forms.NumberInput(attrs={'placeholder': 'MM'})
    )

    duracion = forms.IntegerField(
        min_value=1,
        label='Duración (minutos)',
        widget=forms.NumberInput(attrs={'placeholder': 'Ej. 45'})
    )

    cupo_maximo = forms.IntegerField(
        min_value=1,
        label='Cupo máximo',
        widget=forms.NumberInput(attrs={'placeholder': 'Ej. 20'})
    )

    class Meta:
        model = Class
        fields = ['disciplina', 'sala', 'profesor', 'cupo_maximo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Inicializar sede si se proporciona via GET
        if hasattr(self, 'initial') and 'sede' not in self.initial:
            self.fields['sede'].initial = None

    def clean_hora(self):
        hora = self.cleaned_data.get('hora')
        if hora is not None and not (0 <= hora <= 23):
            raise ValidationError('La hora debe estar entre 0 y 23.')
        return hora

    def clean_minuto(self):
        minuto = self.cleaned_data.get('minuto')
        if minuto is not None and not (0 <= minuto <= 59):
            raise ValidationError('El minuto debe estar entre 0 y 59.')
        return minuto

    def clean(self):
        cleaned_data = super().clean()
        hora = cleaned_data.get('hora')
        minuto = cleaned_data.get('minuto')
        sala = cleaned_data.get('sala')
        profesor = cleaned_data.get('profesor')
        cupo_maximo = cleaned_data.get('cupo_maximo')
        dia_semana = cleaned_data.get('dia_semana')

        # Crear una fecha dummy (próximo día de la semana) para validar
        if hora is not None and minuto is not None and dia_semana is not None:
            try:
                # Crear una fecha dummy para la validación
                from datetime import timedelta as td
                hoy = datetime.now().date()
                dias_adelante = (int(dia_semana) - hoy.weekday()) % 7
                if dias_adelante == 0:
                    dias_adelante = 7
                fecha_dummy = hoy + td(days=dias_adelante)
                inicio = datetime.combine(fecha_dummy, time(hour=int(hora), minute=int(minuto)))
                cleaned_data['inicio'] = inicio
            except (ValueError, TypeError):
                raise ValidationError('Datos de hora inválidos.')

        # Validar que el cupo máximo no exceda la capacidad de la sala
        if sala and cupo_maximo:
            if cupo_maximo > sala.capacidad:
                raise ValidationError(
                    f'El cupo máximo ({cupo_maximo}) no puede exceder la capacidad de la sala ({sala.capacidad}).'
                )

        # Validar que no haya clases que se superpongan
        if cleaned_data.get('inicio') and sala and profesor and dia_semana is not None:
            inicio = cleaned_data.get('inicio')
            # Convertir de formato Python weekday (0-6) a Django iso_week_day (1-7)
            iso_week_day = int(dia_semana) + 1
            
            # Regla 1: No puede haber 2 clases en la misma sede, sala, día y hora
            clases_conflictivas_sala = Class.objects.filter(
                sala=sala,
                inicio__iso_week_day=iso_week_day,
                inicio__hour=inicio.hour,
                inicio__minute=inicio.minute
            )
            
            # Excluir la clase actual si es una edición
            if self.instance.pk:
                clases_conflictivas_sala = clases_conflictivas_sala.exclude(pk=self.instance.pk)
            
            if clases_conflictivas_sala.exists():
                raise ValidationError(
                    f'Ya existe una clase en la sala {sala.nombre} el {dict(self.WEEKDAY_CHOICES)[int(dia_semana)]} a las {inicio.hour:02d}:{inicio.minute:02d}.'
                )
            
            # Regla 2: No puede haber 2 clases con el mismo profesor en el mismo día y hora
            clases_conflictivas_profesor = Class.objects.filter(
                profesor=profesor,
                inicio__iso_week_day=iso_week_day,
                inicio__hour=inicio.hour,
                inicio__minute=inicio.minute
            )
            
            # Excluir la clase actual si es una edición
            if self.instance.pk:
                clases_conflictivas_profesor = clases_conflictivas_profesor.exclude(pk=self.instance.pk)
            
            if clases_conflictivas_profesor.exists():
                raise ValidationError(
                    f'El profesor {profesor.nombre} {profesor.apellido} ya tiene una clase el {dict(self.WEEKDAY_CHOICES)[int(dia_semana)]} a las {inicio.hour:02d}:{inicio.minute:02d}.'
                )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.inicio = self.cleaned_data.get('inicio')
        instance.duracion = timedelta(minutes=self.cleaned_data.get('duracion'))
        
        if commit:
            instance.save()
        return instance


class TeacherForm(forms.ModelForm):
    class Meta:
        model = Teacher
        fields = ['nombre', 'apellido']
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Nombre del profesor'}),
            'apellido': forms.TextInput(attrs={'placeholder': 'Apellido del profesor'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        nombre = cleaned_data.get('nombre')
        apellido = cleaned_data.get('apellido')

        if nombre and apellido:
            # Validar duplicados case-insensitive
            existe = Teacher.objects.filter(
                nombre__iexact=nombre,
                apellido__iexact=apellido
            ).exists()
            if existe:
                raise ValidationError('Ya existe un profesor con ese nombre y apellido.')

        return cleaned_data
