from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone

User = get_user_model()


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "last_name", "dni", "fecha_nacimiento", "telefono_emergencia")
        labels = {
            "email": "Correo electrónico",
            "first_name": "Nombre",
            "last_name": "Apellido",
            "dni": "DNI",
            "fecha_nacimiento": "Fecha de nacimiento",
            "telefono_emergencia": "Teléfono de emergencia",
        }
        widgets = {
            "fecha_nacimiento": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Este correo ya está en uso.", code="email_exists"
            )
        return email

    def clean_dni(self):
        dni = self.cleaned_data.get("dni")
        if User.objects.filter(dni=dni).exists():
            raise forms.ValidationError(
                "Este DNI ya está registrado.", code="dni_exists"
            )
        return dni

    def clean_fecha_nacimiento(self):
        MIN_AGE = 14
        fecha = self.cleaned_data.get("fecha_nacimiento")
        if fecha:
            hoy = timezone.localdate()
            cumple_este_anio = fecha.replace(year=hoy.year)
            edad = hoy.year - fecha.year - (1 if cumple_este_anio > hoy else 0)
            if edad < MIN_AGE:
                raise forms.ValidationError(
                    f"Debés tener al menos {MIN_AGE} años para registrarte.",
                    code="under_age",
                )
        return fecha


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("telefono_emergencia",)
        labels = {"telefono_emergencia": "Teléfono de emergencia"}


class TwoFactorForm(forms.Form):
    code = forms.CharField(
        max_length=6, min_length=6, required=True, label="Código de verificación"
    )

    def __init__(self, *args, **kwargs):
        self.expected_code = kwargs.pop("expected_code", None)
        super().__init__(*args, **kwargs)

    def clean_code(self):
        code = self.cleaned_data.get("code")
        if code != self.expected_code:
            raise forms.ValidationError("El código ingresado es incorrecto.")
        return code
