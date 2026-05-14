from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError

from .models import Class, Teacher

class ClassForm(forms.ModelForm):
    profesor = forms.ModelChoiceField(
        queryset=Teacher.objects.all(),
        label='Profesor',
        empty_label='Selecciona un profesor'
    )
    
    inicio = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={
            'type': 'datetime-local',
        }),
        input_formats=['%Y-%m-%dT%H:%M'],
        label='Inicio'
    )
    duracion = forms.IntegerField(
        min_value=1,
        label='Duración (minutos)',
        widget=forms.NumberInput(attrs={
            'placeholder': 'Ej. 45'
        })
    )
    cupo_maximo = forms.IntegerField(
        min_value=1,
        label='Cupo máximo',
        widget=forms.NumberInput(attrs={
            'placeholder': 'Ej. 20'
        })
    )

    class Meta:
        model = Class
        fields = ['disciplina', 'sala', 'profesor', 'inicio', 'duracion', 'cupo_maximo']
        widgets = {
            'disciplina': forms.Select(),
            'sala': forms.Select(),
        }

    def clean_inicio(self):
        inicio = self.cleaned_data.get('inicio')
        if inicio and inicio.weekday() == 6:
            raise ValidationError('La clase solo puede programarse de lunes a viernes.')
        return inicio

    def clean_duracion(self):
        minutos = self.cleaned_data.get('duracion')
        if minutos is None:
            return minutos
        return timedelta(minutes=minutos)


class TeacherForm(forms.ModelForm):
    class Meta:
        model = Teacher
        fields = ['nombre', 'apellido']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'placeholder': 'Nombre del profesor'
            }),
            'apellido': forms.TextInput(attrs={
                'placeholder': 'Apellido del profesor'
            }),
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
