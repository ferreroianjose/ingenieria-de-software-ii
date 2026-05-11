from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.test import TestCase


# Tests de validación de contraseña (validators.py)
class PasswordValidatorTests(TestCase):
    def test_password_min_length(self):
        # Lo maneja Django, pero dejo el test jic
        with self.assertRaises(ValidationError) as cm:
            validate_password("Ab1!")
        self.assertEqual(cm.exception.error_list[0].code, "password_too_short")

    def test_password_missing_letter(self):
        with self.assertRaises(ValidationError) as cm:
            validate_password("1234567890!")
        # We find our specific code in the list of errors
        codes = [error.code for error in cm.exception.error_list]
        self.assertIn("password_no_letter", codes)

    def test_password_missing_number(self):
        with self.assertRaises(ValidationError) as cm:
            validate_password("abcdefghij!")
        codes = [error.code for error in cm.exception.error_list]
        self.assertIn("password_no_number", codes)

    def test_password_missing_special_character(self):
        with self.assertRaises(ValidationError) as cm:
            validate_password("abcdefghij1")
        codes = [error.code for error in cm.exception.error_list]
        self.assertIn("password_no_special", codes)

    def test_valid_password(self):
        # Should NOT raise ValidationError
        validate_password("ValidPass123!")
