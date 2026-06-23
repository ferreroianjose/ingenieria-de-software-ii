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
        self.assertIn(
            "under_age", [e.code for e in form.errors.as_data()["fecha_nacimiento"]]
        )

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

    def test_create_internal_user_get_page(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("create_internal_user"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/create_internal_user.html")

    def test_create_internal_user_get_htmx(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("create_internal_user"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/_create_user_drawer_panel.html")

    def test_create_internal_user_post_htmx_success(self):
        self.client.force_login(self.staff_user)
        data = {
            "email": "newinternal@example.com",
            "first_name": "Internal",
            "last_name": "User",
            "dni": "88888",
            "fecha_nacimiento": "1995-05-05",
            "rol": "EMPLEADO",
        }
        response = self.client.post(reverse("create_internal_user"), data, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 204)
        self.assertTrue(User.objects.filter(email="newinternal@example.com").exists())

    def test_create_internal_user_post_htmx_invalid(self):
        self.client.force_login(self.staff_user)
        data = {
            "email": "invalidemail",
            "first_name": "Internal",
            "last_name": "User",
            "dni": "88888",
            "fecha_nacimiento": "1995-05-05",
            "rol": "EMPLEADO",
        }
        response = self.client.post(reverse("create_internal_user"), data, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/_create_user_drawer_panel.html")
        self.assertTrue(response.context["form"].errors)

    def test_user_detail_drawer_get(self):
        self.client.force_login(self.staff_user)
        response = self.client.get(reverse("user_detail_drawer", args=[self.client_user.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/_user_detail_drawer_panel.html")


from apps.users.forms import UserAdminUpdateForm, InternalUserCreationForm
from apps.users.tasks import clean_unverified_users
from django.utils import timezone


class UserAdminUpdateFormTests(TestCase):
    def setUp(self):
        self.client_user = User.objects.create(
            email="c@example.com", username="c@example.com", dni="1", rol="CLIENTE"
        )
        self.admin_user = User.objects.create(
            email="a@example.com", username="a@example.com", dni="2", rol="ADMIN"
        )
        self.emp_user = User.objects.create(
            email="e@example.com", username="e@example.com", dni="3", rol="EMPLEADO"
        )

    def test_client_cannot_become_admin_or_employee(self):
        data = {"first_name": "C", "last_name": "C", "email": "c@example.com", "dni": "1", "rol": "ADMIN", "estado_constancia": "PENDIENTE"}
        form = UserAdminUpdateForm(data, instance=self.client_user)
        self.assertFalse(form.is_valid())
        self.assertIn("Un cliente no puede convertirse", form.errors["rol"][0])

        data["rol"] = "EMPLEADO"
        form = UserAdminUpdateForm(data, instance=self.client_user)
        self.assertFalse(form.is_valid())
        self.assertIn("Un cliente no puede convertirse", form.errors["rol"][0])

    def test_admin_cannot_become_client(self):
        data = {"first_name": "A", "last_name": "A", "email": "a@example.com", "dni": "2", "rol": "CLIENTE", "estado_constancia": "PENDIENTE"}
        form = UserAdminUpdateForm(data, instance=self.admin_user)
        self.assertFalse(form.is_valid())
        self.assertIn("no puede convertirse en cliente", form.errors["rol"][0])

    def test_admin_can_become_employee(self):
        data = {"first_name": "A", "last_name": "A", "email": "a@example.com", "dni": "2", "rol": "EMPLEADO", "estado_constancia": "PENDIENTE"}
        form = UserAdminUpdateForm(data, instance=self.admin_user)
        self.assertTrue(form.is_valid())

    def test_employee_cannot_become_client(self):
        data = {"first_name": "E", "last_name": "E", "email": "e@example.com", "dni": "3", "rol": "CLIENTE", "estado_constancia": "PENDIENTE"}
        form = UserAdminUpdateForm(data, instance=self.emp_user)
        self.assertFalse(form.is_valid())
        self.assertIn("no puede convertirse en cliente", form.errors["rol"][0])

    def test_employee_can_become_admin(self):
        data = {"first_name": "E", "last_name": "E", "email": "e@example.com", "dni": "3", "rol": "ADMIN", "estado_constancia": "PENDIENTE"}
        form = UserAdminUpdateForm(data, instance=self.emp_user)
        self.assertTrue(form.is_valid())


class InternalUserCreationFormTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create(
            email="admin@gym.com", username="admin", rol="ADMIN", dni="99"
        )
        self.emp_user = User.objects.create(
            email="emp@gym.com", username="emp", rol="EMPLEADO", dni="88"
        )

    def test_employee_can_only_create_clients(self):
        form = InternalUserCreationForm(creator=self.emp_user)
        choices = [c[0] for c in form.fields["rol"].choices]
        self.assertEqual(choices, ["CLIENTE"])
        self.assertEqual(form.fields["rol"].initial, "CLIENTE")

    def test_admin_can_create_all_roles(self):
        form = InternalUserCreationForm(creator=self.admin_user)
        choices = [c[0] for c in form.fields["rol"].choices]
        self.assertEqual(choices, ["CLIENTE", "EMPLEADO", "ADMIN"])


class TasksTests(TestCase):
    def test_clean_unverified_users(self):
        # Create an old verified user
        old_verified = User.objects.create(
            email="old1@example.com", username="old1", dni="old1"
        )
        old_verified.set_password("validpass123")
        old_verified.save()
        old_verified.date_joined = timezone.now() - timedelta(days=3)
        old_verified.save()

        # Create an old unverified user
        old_unverified = User.objects.create(
            email="old2@example.com", username="old2", dni="old2"
        )
        old_unverified.set_unusable_password()
        old_unverified.save()
        old_unverified.date_joined = timezone.now() - timedelta(days=3)
        old_unverified.save()

        # Create a new unverified user (less than 48 hours)
        new_unverified = User.objects.create(
            email="new1@example.com", username="new1", dni="new1"
        )
        new_unverified.set_unusable_password()
        new_unverified.save()
        new_unverified.date_joined = timezone.now() - timedelta(hours=24)
        new_unverified.save()

        result = clean_unverified_users()
        self.assertIn("1 usuarios eliminados", result)

        self.assertTrue(User.objects.filter(email="old1@example.com").exists())
        self.assertFalse(User.objects.filter(email="old2@example.com").exists())
        self.assertTrue(User.objects.filter(email="new1@example.com").exists())
