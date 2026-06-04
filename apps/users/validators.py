import re

from django.contrib.auth.password_validation import (
    CommonPasswordValidator as DjangoCommonPasswordValidator,
    MinimumLengthValidator as DjangoMinimumLengthValidator,
    NumericPasswordValidator as DjangoNumericPasswordValidator,
    UserAttributeSimilarityValidator as DjangoUserAttributeSimilarityValidator,
)
from django.core.exceptions import ValidationError


def _spanish_password_validation_error(exc: ValidationError) -> ValidationError:
    """Reemplaza mensajes gettext de Django por strings fijas en español."""
    translated = []
    for error in exc.error_list:
        code = error.code
        params = error.params or {}
        if code == "password_too_short":
            min_length = params.get("min_length", 10)
            translated.append(
                ValidationError(
                    (
                        "La contraseña es demasiado corta. Debe contener por lo menos "
                        f"{min_length} caracteres."
                    ),
                    code=code,
                )
            )
        elif code == "password_too_common":
            translated.append(
                ValidationError(
                    "La contraseña tiene un valor demasiado común.",
                    code=code,
                )
            )
        elif code == "password_entirely_numeric":
            translated.append(
                ValidationError(
                    "La contraseña está formada completamente por dígitos.",
                    code=code,
                )
            )
        elif code == "password_too_similar":
            verbose_name = str(params.get("verbose_name", "tu información personal"))
            label = _similar_attribute_label(verbose_name)
            translated.append(
                ValidationError(
                    f"La contraseña es muy similar a {label}.",
                    code=code,
                )
            )
        else:
            translated.append(error)
    if len(translated) == 1:
        return translated[0]
    return ValidationError(translated)


def _similar_attribute_label(verbose_name: str) -> str:
    key = verbose_name.lower().strip()
    return {
        "email address": "tu correo electrónico",
        "dirección de email": "tu correo electrónico",
        "nombre de usuario": "tu correo electrónico",
        "username": "tu correo electrónico",
        "nombre": "tu nombre",
        "first name": "tu nombre",
        "apellido": "tu apellido",
        "last name": "tu apellido",
    }.get(key, verbose_name)


class _SpanishPasswordValidatorMixin:
    def validate(self, password, user=None):
        try:
            super().validate(password, user)
        except ValidationError as exc:
            raise _spanish_password_validation_error(exc) from None


class MinimumLengthValidator(
    _SpanishPasswordValidatorMixin, DjangoMinimumLengthValidator
):
    def get_help_text(self):
        return (
            f"Su contraseña debe contener por lo menos {self.min_length} caracteres."
        )


class UserAttributeSimilarityValidator(
    _SpanishPasswordValidatorMixin, DjangoUserAttributeSimilarityValidator
):
    def get_help_text(self):
        return (
            "Su contraseña no puede ser similar a otros componentes de su "
            "información personal."
        )


class CommonPasswordValidator(
    _SpanishPasswordValidatorMixin, DjangoCommonPasswordValidator
):
    def get_help_text(self):
        return "Su contraseña no puede ser una contraseña usada muy comúnmente."


class NumericPasswordValidator(
    _SpanishPasswordValidatorMixin, DjangoNumericPasswordValidator
):
    def get_help_text(self):
        return "Su contraseña no puede estar formada exclusivamente por números."


class LetterValidator:
    def validate(self, password, user=None):
        if not re.search(r"[a-zA-Z]", password):
            raise ValidationError(
                "La contraseña debe contener al menos una letra.",
                code="password_no_letter",
            )

    def get_help_text(self):
        return "Su contraseña debe contener al menos una letra."


class NumberValidator:
    def validate(self, password, user=None):
        if not re.search(r"[0-9]", password):
            raise ValidationError(
                "La contraseña debe contener al menos un número.",
                code="password_no_number",
            )

    def get_help_text(self):
        return "Su contraseña debe contener al menos un número."


class SpecialCharacterValidator:
    def validate(self, password, user=None):
        if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\];:\']', password):
            raise ValidationError(
                "La contraseña debe contener al menos un carácter especial.",
                code="password_no_special",
            )

    def get_help_text(self):
        return "Su contraseña debe contener al menos un carácter especial."


class NameValidator:
    def validate(self, value, user=None):
        if not re.match(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑ\s\-']+$", value):
            raise ValidationError(
                "El nombre y apellido solo pueden contener letras, espacios, guiones y apóstrofes.",
                code="invalid_name",
            )

    def get_help_text(self):
        return "Solo se permiten letras, espacios, guiones y apóstrofes."
