from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError

from .models import Class

class ClassForm(forms.ModelForm):
    inicio = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={
            'type': 'datetime-local',
            'class': 'w-full rounded-full border border-gray-200 px-4 py-3 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary-400',
        }),
        input_formats=['%Y-%m-%dT%H:%M'],
        label='Inicio'
    )
    duracion = forms.IntegerField(
        min_value=1,
        label='Duración (minutos)',
        widget=forms.NumberInput(attrs={
            'class': 'w-full rounded-full border border-gray-200 px-4 py-3 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary-400',
            'placeholder': 'Ej. 45'
        })
    )
    cupo_maximo = forms.IntegerField(
        min_value=1,
        label='Cupo máximo',
        widget=forms.NumberInput(attrs={
            'class': 'w-full rounded-full border border-gray-200 px-4 py-3 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary-400',
            'placeholder': 'Ej. 20'
        })
    )

    class Meta:
        model = Class
        fields = ['disciplina', 'sala', 'profesor', 'inicio', 'duracion', 'cupo_maximo']
        widgets = {
            'disciplina': forms.Select(attrs={
                'class': 'w-full rounded-full border border-gray-200 px-4 py-3 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary-400'
            }),
            'sala': forms.Select(attrs={
                'class': 'w-full rounded-full border border-gray-200 px-4 py-3 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary-400'
            }),
            'profesor': forms.TextInput(attrs={
                'class': 'w-full rounded-full border border-gray-200 px-4 py-3 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary-400',
                'placeholder': 'Nombre del profesor'
            }),
        }

    def clean_inicio(self):
        inicio = self.cleaned_data.get('inicio')
        if inicio and inicio.weekday() == 6:
            raise ValidationError('La clase solo puede programarse de lunes a sábado.')
        return inicio

    def clean_duracion(self):
        minutos = self.cleaned_data.get('duracion')
        if minutos is None:
            return minutos
        return timedelta(minutes=minutos)
