from datetime import date, timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.password_validation import validate_password

from apps.users.forms import (
    CustomUserCreationForm,
    GymAuthenticationForm,
    LOGIN_INVALID_MESSAGE,
)

User = get_user_model()


# Tests de validación de contraseña (validators.py)
class PasswordValidatorTests(TestCase):
    def test_password_min_length(self):
        with self.assertRaises(ValidationError) as cm:
            validate_password("Ab1!")
        error = cm.exception.error_list[0]
        self.assertEqual(error.code, "password_too_short")
        self.assertIn("demasiado corta", str(error.message))

    def test_password_too_common_message(self):
        from apps.users.validators import CommonPasswordValidator

        with self.assertRaises(ValidationError) as cm:
            CommonPasswordValidator().validate("password")
        error = cm.exception.error_list[0]
        self.assertEqual(error.code, "password_too_common")
        self.assertEqual(
            str(error.message),
            "La contraseña tiene un valor demasiado común.",
        )

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


class UserModelTests(TestCase):
    def test_user_creation_syncs_username_with_email(self):
        email = "test@example.com"
        user = User.objects.create(email=email, username=email, dni="12345678")
        self.assertEqual(user.username, email)

    def test_superuser_role_is_admin(self):
        user = User.objects.create_superuser(
            email="admin@example.com",
            username="admin@example.com",
            password="password123",
            dni="87654321",
        )
        self.assertEqual(user.rol, "ADMIN")

    def test_user_str_representation(self):
        user = User(email="test@example.com", first_name="Juan", last_name="Perez")
        self.assertEqual(str(user), "Juan Perez (test@example.com)")


class CustomUserCreationFormTests(TestCase):
    def test_form_validation_min_age(self):
        # 13 years ago from today
        dob = date.today() - timedelta(days=365 * 13)
        data = {
            "email": "young@example.com",
            "first_name": "Young",
            "last_name": "User",
            "dni": "11223344",
            "fecha_nacimiento": dob,
            "password1": "ValidPass123!",
            "password2": "ValidPass123!",
        }
        form = CustomUserCreationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("under_age", [e.code for e in form.errors.as_data()["fecha_nacimiento"]])

    def test_form_validation_duplicate_email(self):
        User.objects.create(
            email="duplicate@example.com", username="duplicate@example.com", dni="1234"
        )
        data = {
            "email": "duplicate@example.com",
            "first_name": "Test",
            "last_name": "User",
            "dni": "5678",
            "fecha_nacimiento": "1990-01-01",
            "password1": "ValidPass123!",
            "password2": "ValidPass123!",
        }
        form = CustomUserCreationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("email_exists", [e.code for e in form.errors.as_data()["email"]])

    def test_form_validation_duplicate_dni(self):
        User.objects.create(
            email="user1@example.com", username="user1@example.com", dni="12345678"
        )
        data = {
            "email": "user2@example.com",
            "first_name": "Test",
            "last_name": "User",
            "dni": "12345678",
            "fecha_nacimiento": "1990-01-01",
            "password1": "ValidPass123!",
            "password2": "ValidPass123!",
        }
        form = CustomUserCreationForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("dni_exists", [e.code for e in form.errors.as_data()["dni"]])


class GymAuthenticationFormTests(TestCase):
    def test_invalid_login_message(self):
        form = GymAuthenticationForm(
            data={"username": "wrong@example.com", "password": "wrongpass"}
        )
        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.non_field_errors()[0],
            LOGIN_INVALID_MESSAGE,
        )


class UserViewsTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            email="staff@example.com",
            username="staff@example.com",
            password="password123",
            dni="111",
            rol="ADMIN",
        )
        self.client_user = User.objects.create_user(
            email="client@example.com",
            username="client@example.com",
            password="password123",
            dni="222",
        )

    def test_login_staff_redirects_to_2fa(self):
        response = self.client.post(
            reverse("login"),
            {"username": "staff@example.com", "password": "password123"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("two_factor"), response.url)
        self.assertTrue(self.client.session.get("is_2fa_pending"))

    def test_login_client_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("login"),
            {"username": "client@example.com", "password": "password123"},
        )
        self.assertRedirects(response, reverse("dashboard"))

    def test_login_wrong_password_shows_spanish_message(self):
        response = self.client.post(
            reverse("login"),
            {"username": "client@example.com", "password": "wrong"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, LOGIN_INVALID_MESSAGE)

    def test_two_factor_view_requires_pending_session(self):
        self.client.login(username="staff@example.com", password="password123")
        response = self.client.get(reverse("two_factor"))
        self.assertRedirects(response, reverse("dashboard"))

    def test_two_factor_view_post_completes_login(self):
        code = "123456"
        self.client.login(username="staff@example.com", password="password123")
        session = self.client.session
        session["is_2fa_pending"] = True
        session["2fa_code"] = code
        session.save()

        response = self.client.post(reverse("two_factor"), {"code": code})
        self.assertRedirects(response, reverse("dashboard"))
        self.assertNotIn("is_2fa_pending", self.client.session)

    def test_register_authenticated_user_redirects(self):
        self.client.login(username="client@example.com", password="password123")
        response = self.client.get(reverse("register"))
        self.assertRedirects(response, reverse("dashboard"))

    def test_register_successful(self):
        data = {
            "email": "newuser@example.com",
            "first_name": "New",
            "last_name": "User",
            "dni": "99999",
            "fecha_nacimiento": "1990-01-01",
            "password1": "NewPass123!",
            "password2": "NewPass123!",
        }
        response = self.client.post(reverse("register"), data)
        self.assertRedirects(response, reverse("dashboard"))
        self.assertTrue(User.objects.filter(email="newuser@example.com").exists())
