import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class LetterValidator:
    def validate(self, password, user=None):
        if not re.search(r"[a-zA-Z]", password):
            raise ValidationError(
                _("La contraseña debe contener al menos una letra."),
                code="password_no_letter",
            )

    def get_help_text(self):
        return _("Su contraseña debe contener al menos una letra.")


class NumberValidator:
    def validate(self, password, user=None):
        if not re.search(r"[0-9]", password):
            raise ValidationError(
                _("La contraseña debe contener al menos un número."),
                code="password_no_number",
            )

    def get_help_text(self):
        return _("Su contraseña debe contener al menos un número.")


class SpecialCharacterValidator:
    def validate(self, password, user=None):
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise ValidationError(
                _("La contraseña debe contener al menos un carácter especial."),
                code="password_no_special",
            )

    def get_help_text(self):
        return _("Su contraseña debe contener al menos un carácter especial.")
