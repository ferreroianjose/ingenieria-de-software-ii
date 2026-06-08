from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone

from GYMFlow.forms import apply_required_error_messages

from .validators import NameValidator

User = get_user_model()
name_validator = NameValidator()

LOGIN_INVALID_MESSAGE = (
    "Por favor introduzca un correo electrónico y una contraseña correctos. "
    "Tenga en cuenta que ambos campos son sensibles a mayúsculas/minúsculas."
)
LOGIN_INACTIVE_MESSAGE = "Esta cuenta está inactiva."


class GymAuthenticationForm(AuthenticationForm):
    error_messages = {
        "invalid_login": LOGIN_INVALID_MESSAGE,
        "inactive": LOGIN_INACTIVE_MESSAGE,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Correo electrónico"
        self.fields["password"].label = "Contraseña"
        apply_required_error_messages(self)

    def get_invalid_login_error(self):
        return ValidationError(
            self.error_messages["invalid_login"],
            code="invalid_login",
        )


class CustomUserCreationForm(UserCreationForm):
    error_messages = {
        "password_mismatch": (
            "Los dos campos de contraseñas no coinciden entre si."
        ),
    }

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "Contraseña"
        self.fields["password2"].label = "Confirmación de contraseña"
        apply_required_error_messages(self)

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Este correo ya está en uso.", code="email_exists"
            )
        return email

    def clean_first_name(self):
        first_name = self.cleaned_data.get("first_name")
        if first_name:
            name_validator.validate(first_name)
        return first_name

    def clean_last_name(self):
        last_name = self.cleaned_data.get("last_name")
        if last_name:
            name_validator.validate(last_name)
        return last_name

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

    def clean_telefono_emergencia(self):
        telefono = self.cleaned_data.get("telefono_emergencia")
        if telefono:
            import re
            if not re.match(r'^[\d\+\-\s\(\)]*$', telefono):
                raise forms.ValidationError("El teléfono no puede contener letras, solo números y los símbolos + o -.")
        return telefono


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("telefono_emergencia",)
        labels = {"telefono_emergencia": "Teléfono de emergencia"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_required_error_messages(self)

    def clean_telefono_emergencia(self):
        telefono = self.cleaned_data.get("telefono_emergencia")
        if telefono:
            import re
            if not re.match(r'^[\d\+\-\s\(\)]*$', telefono):
                raise forms.ValidationError("El teléfono no puede contener letras, solo números y los símbolos + o -.")
        return telefono


class TwoFactorForm(forms.Form):
    code = forms.CharField(
        max_length=6, min_length=6, required=True, label="Código de verificación"
    )

    def __init__(self, *args, **kwargs):
        self.expected_code = kwargs.pop("expected_code", None)
        super().__init__(*args, **kwargs)
        apply_required_error_messages(self)

    def clean_code(self):
        code = self.cleaned_data.get("code")
        if code != self.expected_code:
            raise forms.ValidationError("El código ingresado es incorrecto.")
        return code
