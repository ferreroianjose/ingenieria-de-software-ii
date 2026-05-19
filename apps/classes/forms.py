from datetime import timedelta, datetime, time

from django import forms
from django.core.exceptions import ValidationError

from .models import Class, Teacher, Sede, Sala, Disciplina


class BaseStyledForm(forms.ModelForm):
    """Base form to handle custom required error messages with labels"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if field.required:
                field.error_messages['required'] = f'El campo "{field.label}" es obligatorio.'


class SedeForm(BaseStyledForm):
    class Meta:
        model = Sede
        fields = ['nombre', 'direccion']
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Nombre de la sede'}),
            'direccion': forms.TextInput(attrs={'placeholder': 'Dirección'}),
        }


class DisciplinaForm(BaseStyledForm):
    class Meta:
        model = Disciplina
        fields = ['nombre', 'descripcion']
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Nombre de la disciplina'}),
            'descripcion': forms.Textarea(attrs={'placeholder': 'Descripción', 'rows': 3}),
        }


class SalaForm(BaseStyledForm):
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


class ClassForm(BaseStyledForm):
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
        empty_label='Selecciona una sala',
    )

    profesor = forms.ModelChoiceField(
        queryset=Teacher.objects.all(),
        label='Profesor',
        empty_label='Selecciona un profesor'
    )

    dia_semana = forms.ChoiceField(
        choices=Class.WEEKDAY_CHOICES,
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

    duracion_minutos = forms.IntegerField(
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
        fields = ['disciplina', 'sala', 'profesor', 'dia_semana', 'cupo_maximo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.urls import reverse
        self.fields['sede'].widget.attrs.update({
            'hx-get': reverse('classes:salas_por_sede'),
            'hx-target': '#sala-field-container',
            'hx-swap': 'innerHTML',
            'hx-trigger': 'change',
            'hx-include': 'this',
            # Modal form sets hx-select="#showModal-container"; unset avoids empty swaps.
            'hx-select': 'unset',
        })

        sede_id = self._resolve_sede_id()
        if sede_id:
            self.fields['sala'].queryset = Sala.objects.filter(
                sede_id=sede_id
            ).order_by('nombre')
            if 'sede' not in self.initial and not self.data:
                self.fields['sede'].initial = sede_id
        else:
            self.fields['sala'].queryset = Sala.objects.none()

        if self.instance.pk and self.instance.duracion and not self.data:
            self.fields['duracion_minutos'].initial = self.instance.duracion_minutos

    def _resolve_sede_id(self):
        if 'sede' in self.data:
            try:
                return int(self.data.get('sede'))
            except (ValueError, TypeError):
                return None
        sede = self.initial.get('sede')
        if sede is not None:
            try:
                return int(sede)
            except (ValueError, TypeError):
                return None
        if self.instance.pk and self.instance.sala_id:
            return self.instance.sala.sede_id
        return None

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
        sede = cleaned_data.get('sede')
        duracion_min = cleaned_data.get('duracion_minutos')

        # Validate that the sala belongs to the selected sede
        if sala and sede and sala.sede != sede:
            raise ValidationError(f'La sala {sala.nombre} no pertenece a la sede {sede.nombre}.')

        if hora is not None and minuto is not None and duracion_min is not None:
            try:
                hora_inicio = time(hour=int(hora), minute=int(minuto))
                cleaned_data['hora_inicio'] = hora_inicio
                # Calculate time overlap by creating dummy dates on the same day
                dummy_date = datetime.today().date()
                inicio_dt = datetime.combine(dummy_date, hora_inicio)
                fin_dt = inicio_dt + timedelta(minutes=duracion_min)
                cleaned_data['inicio_dt'] = inicio_dt
                cleaned_data['fin_dt'] = fin_dt
            except ValueError:
                raise ValidationError('Datos de hora o duración inválidos.')

        if sala and cupo_maximo:
            if cupo_maximo > sala.capacidad:
                raise ValidationError(
                    f'El cupo máximo ({cupo_maximo}) no puede exceder la capacidad de la sala ({sala.capacidad}).'
                )

        if cleaned_data.get('hora_inicio') and sala and profesor and dia_semana is not None:
            dummy_date = datetime.today().date()
            inicio_dt = cleaned_data.get('inicio_dt')
            fin_dt = cleaned_data.get('fin_dt')
            
            # Since TimeField logic is tricky, we can do it in python memory for that specific day, sala or professor
            # Get all classes for the same day and sala
            clases_mismo_dia_sala = Class.objects.filter(
                sala=sala,
                dia_semana=dia_semana
            )
            if self.instance.pk:
                clases_mismo_dia_sala = clases_mismo_dia_sala.exclude(pk=self.instance.pk)

            for c in clases_mismo_dia_sala:
                if not c.hora_inicio:
                    continue
                c_inicio = datetime.combine(dummy_date, c.hora_inicio)
                c_fin = c_inicio + c.duracion
                # Overlap check
                if inicio_dt < c_fin and fin_dt > c_inicio:
                    raise ValidationError(
                        f'Superposición con otra clase en {sala.nombre} de {c.hora_inicio.strftime("%H:%M")} a {c_fin.strftime("%H:%M")}.'
                    )
            
            # Get all classes for the same day and professor
            clases_mismo_dia_prof = Class.objects.filter(
                profesor=profesor,
                dia_semana=dia_semana
            )
            if self.instance.pk:
                clases_mismo_dia_prof = clases_mismo_dia_prof.exclude(pk=self.instance.pk)

            for c in clases_mismo_dia_prof:
                if not c.hora_inicio:
                    continue
                c_inicio = datetime.combine(dummy_date, c.hora_inicio)
                c_fin = c_inicio + c.duracion
                if inicio_dt < c_fin and fin_dt > c_inicio:
                    raise ValidationError(
                        f'El profesor {profesor.nombre} {profesor.apellido} ya tiene una clase de {c.hora_inicio.strftime("%H:%M")} a {c_fin.strftime("%H:%M")}.'
                    )

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.hora_inicio = self.cleaned_data.get('hora_inicio')
        instance.duracion = timedelta(
            minutes=self.cleaned_data['duracion_minutos']
        )
        
        if commit:
            instance.save()
        return instance


class TeacherForm(BaseStyledForm):
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
