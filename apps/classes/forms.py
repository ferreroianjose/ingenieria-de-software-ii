from datetime import timedelta, datetime, time

from django import forms
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models

from apps.core.forms import apply_required_error_messages

from .models import Class, Teacher, Sede, Sala, Disciplina


class BaseStyledForm(forms.ModelForm):
    """Base form to handle custom required error messages with labels."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_required_error_messages(self)


class SedeForm(BaseStyledForm):
    class Meta:
        model = Sede
        fields = ['nombre', 'direccion']
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Nombre de la sede'}),
            'direccion': forms.TextInput(attrs={'placeholder': 'Dirección'}),
        }

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        if nombre:
            existe = Sede.objects.filter(nombre__iexact=nombre).exclude(pk=self.instance.pk).exists()
            if existe:
                raise ValidationError('Ya existe una sede con ese nombre.')
        return nombre


class DisciplinaForm(BaseStyledForm):
    class Meta:
        model = Disciplina
        fields = ['nombre', 'descripcion']
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Nombre de la disciplina'}),
            'descripcion': forms.Textarea(attrs={'placeholder': 'Descripción', 'rows': 3}),
        }

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        if nombre:
            existe = Disciplina.objects.filter(nombre__iexact=nombre).exclude(pk=self.instance.pk).exists()
            if existe:
                raise ValidationError('Ya existe una disciplina con ese nombre.')
        return nombre


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

    def clean(self):
        # Validamos a nivel form (no `clean_nombre`) porque `sede` se declara
        # después de `nombre` y todavía no estaría en `cleaned_data` en una
        # validación por campo. Acá ya están ambos limpios.
        cleaned = super().clean()
        nombre = cleaned.get('nombre')
        sede = cleaned.get('sede')
        if nombre and sede:
            existe = (
                Sala.objects.filter(nombre__iexact=nombre, sede=sede)
                .exclude(pk=self.instance.pk)
                .exists()
            )
            if existe:
                self.add_error(
                    'nombre',
                    ValidationError('Ya existe una sala con ese nombre en esta sede.'),
                )
        return cleaned

    def clean_capacidad(self):
        capacidad = self.cleaned_data.get('capacidad')
        if capacidad is not None and capacidad <= 0:
            raise ValidationError('La capacidad debe ser mayor a 0.')

        if self.instance.pk and capacidad:
            max_cupo = Class.objects.filter(sala=self.instance).aggregate(max_cupo=models.Max('cupo_maximo'))['max_cupo']
            if max_cupo and capacidad < max_cupo:
                raise ValidationError(
                    f'La capacidad ({capacidad}) no puede ser menor que el cupo máximo de las clases existentes ({max_cupo}).'
                )

        return capacidad


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

    precio = forms.DecimalField(
        min_value=0, decimal_places=2, max_digits=10, label='Precio',
        widget=forms.NumberInput(attrs={'step': '100', 'placeholder': 'Ej. 2500'})
    )

    mes_a_aplicar = forms.ModelChoiceField(
        queryset=None, # Set in __init__
        label='Aplicar desde el mes',
        required=False,
        empty_label=None
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

        from apps.payments.models import PeriodoCobro, PrecioClase
        from django.utils import timezone
        
        hoy = timezone.localdate()
        periodos_futuros = PeriodoCobro.objects.filter(
            fecha_fin_periodo__gte=hoy
        ).order_by('fecha_inicio_periodo')
        
        self.fields['mes_a_aplicar'].queryset = periodos_futuros
        
        if self.instance.pk:
            self.fields['precio'].label = 'Precio de la clase'
            from django.urls import reverse
            self.fields['mes_a_aplicar'].widget.attrs.update({
                'hx-get': reverse('classes:class_price_for_period', args=[self.instance.pk]),
                'hx-target': '#id_precio',
                'hx-swap': 'outerHTML',
            })
            if periodos_futuros.exists():
                primer_futuro = periodos_futuros.first()
                self.fields['mes_a_aplicar'].initial = primer_futuro.id
                
                if not self.data:
                    precio_obj = PrecioClase.objects.filter(clase=self.instance, periodo=primer_futuro).first()
                    if precio_obj:
                        self.fields['precio'].initial = precio_obj.monto
        else:
            self.fields['precio'].label = 'Precio inicial'
            self.fields['mes_a_aplicar'].widget = forms.HiddenInput()

        if self.instance.pk and self.instance.duracion and not self.data:
            self.fields['duracion_minutos'].initial = self.instance.duracion_minutos

        # Apply restricted schedule if configured
        if getattr(settings, 'GYM_RESTRICTED_SCHEDULE', False):
            self.fields['minuto'].widget = forms.HiddenInput()
            self.fields['minuto'].initial = 0
            self.fields['minuto'].required = False

            self.fields['duracion_minutos'].widget = forms.HiddenInput()
            self.fields['duracion_minutos'].initial = 60
            self.fields['duracion_minutos'].required = False
        else:
            # Revert to visible if setting is off (useful if toggled)
            self.fields['duracion_minutos'].widget = forms.NumberInput(attrs={'placeholder': 'Ej. 45'})
            self.fields['duracion_minutos'].initial = 60 # Default to 60 as per previous requirement but editable

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
        if getattr(settings, 'GYM_RESTRICTED_SCHEDULE', False):
            return 0
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

        if getattr(settings, 'GYM_RESTRICTED_SCHEDULE', False):
            minuto = 0
            duracion_min = 60
            cleaned_data['minuto'] = minuto
            cleaned_data['duracion_minutos'] = duracion_min

        # Validate that the sala belongs to the selected sede
        if sala and sede and sala.sede != sede:
            raise ValidationError(f'La sala {sala.nombre} no pertenece a la sede {sede.nombre}.')

        if hora is not None and minuto is not None:
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
        is_new = self.instance.pk is None
        instance = super().save(commit=False)
        instance.hora_inicio = self.cleaned_data.get('hora_inicio')

        duracion_min = self.cleaned_data.get('duracion_minutos')
        if getattr(settings, 'GYM_RESTRICTED_SCHEDULE', False):
            duracion_min = 60

        instance.duracion = timedelta(minutes=duracion_min)

        if commit:
            instance.save()
            
            precio = self.cleaned_data.get('precio')
            if precio is not None:
                from apps.payments.models import PeriodoCobro, PrecioClase
                from django.utils import timezone
                
                mes_a_aplicar = self.cleaned_data.get('mes_a_aplicar')
                
                if not is_new and mes_a_aplicar:
                    periodos_a_afectar = PeriodoCobro.objects.filter(
                        fecha_inicio_periodo__gte=mes_a_aplicar.fecha_inicio_periodo
                    )
                else:
                    hoy = timezone.localdate()
                    periodos_a_afectar = PeriodoCobro.objects.filter(
                        fecha_fin_periodo__gte=hoy
                    )
                
                for periodo in periodos_a_afectar:
                    PrecioClase.objects.update_or_create(
                        clase=instance,
                        periodo=periodo,
                        defaults={'monto': precio}
                    )

        return instance


class TeacherForm(BaseStyledForm):
    class Meta:
        model = Teacher
        fields = ['nombre', 'apellido']
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Nombre del profesor'}),
            'apellido': forms.TextInput(attrs={'placeholder': 'Apellido del profesor'}),
        }

    def validate_unique(self):
        """Un solo mensaje amigable; evita duplicar el error de unique_together del modelo."""
        nombre = self.cleaned_data.get('nombre')
        apellido = self.cleaned_data.get('apellido')
        if not nombre or not apellido:
            return
        qs = Teacher.objects.filter(
            nombre__iexact=nombre,
            apellido__iexact=apellido,
        )
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            self.add_error(None, 'Ya existe un profesor con ese nombre y apellido.')
