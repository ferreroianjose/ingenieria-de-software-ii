from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

User = get_user_model()


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "last_name", "dni", "fecha_nacimiento")
        labels = {
            "email": "Correo electrónico",
            "first_name": "Nombre",
            "last_name": "Apellido",
            "dni": "DNI",
            "fecha_nacimiento": "Fecha de nacimiento",
        }
        widgets = {
            "fecha_nacimiento": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Este correo ya está en uso.")
        return email

    def clean_dni(self):
        dni = self.cleaned_data.get("dni")
        if User.objects.filter(dni=dni).exists():
            raise forms.ValidationError("Este DNI ya está registrado.")
        return dni
