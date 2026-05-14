from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import transaction
from django.test import TransactionTestCase, override_settings

from apps.notifications.adapters.email import (
    EmailNotificationAdapter,
    FakeEmailNotificationAdapter,
)
from apps.notifications.services import NotificationService

User = get_user_model()


class MockNotifiable:
    """Objeto simple que no es un modelo pero implementa el protocolo."""

    def get_notification_contact(self, channel_slug):
        if channel_slug in ["email", "fake_email"]:
            return "mock@example.com"
        return "555-1234"


class NotificationSystemTest(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser@example.com",
            email="testuser@example.com",
            password="password123",
            first_name="Test",
            last_name="User",
        )

        # Sobreescribimos el backend para los tests para usar locmem
        self.fake_adapter = FakeEmailNotificationAdapter()
        self.fake_adapter.backend = "django.core.mail.backends.locmem.EmailBackend"

        self.email_adapter = EmailNotificationAdapter()
        self.email_adapter.backend = "django.core.mail.backends.locmem.EmailBackend"

        self.service = NotificationService(
            adapters=[self.fake_adapter, self.email_adapter]
        )

    def test_user_notifiable_protocol(self):
        """Verifica que el modelo User implementa correctamente el protocolo."""
        self.assertEqual(self.user.get_notification_contact("email"), self.user.email)
        self.assertEqual(
            self.user.get_notification_contact("fake_email"), self.user.email
        )
        self.assertEqual(self.user.get_notification_contact("sms"), "")

    def test_non_model_notifiable_protocol(self):
        """Verifica que el protocolo funciona con cualquier objeto que implemente el método."""
        mock = MockNotifiable()
        results = self.service.notify(
            recipient=mock, subject="Mock", message="Test", use_transaction=False
        )
        self.assertTrue(results["email"])
        self.assertEqual(mail.outbox[0].to, ["mock@example.com"])

    def test_notify_with_user_object(self):
        """Verifica el envío usando un objeto User."""
        results = self.service.notify(
            recipient=self.user,
            subject="Test Subject",
            message="Test Message",
            use_transaction=False,
        )

        self.assertTrue(results["fake_email"])
        self.assertTrue(results["email"])
        self.assertEqual(len(mail.outbox), 2)

    def test_notify_with_html_message(self):
        """Verifica que el adaptador de email maneja correctamente el contenido HTML."""
        html_content = "<h1>Hola</h1>"
        self.service.notify(
            recipient="test@example.com",
            subject="HTML",
            message="Texto plano",
            html_message=html_content,
            use_transaction=False,
        )

        msg = mail.outbox[0]
        # El primer mensaje (fake_email) debería tener el alternative
        self.assertEqual(len(msg.alternatives), 1)
        self.assertEqual(msg.alternatives[0][0], html_content)
        self.assertEqual(msg.alternatives[0][1], "text/html")

    def test_transaction_on_commit_behavior(self):
        """Verifica que con use_transaction=True, el envío se pospone al commit."""
        with transaction.atomic():
            self.service.notify(
                recipient=self.user,
                subject="Deferred",
                message="Wait",
                use_transaction=True,
            )
            self.assertEqual(len(mail.outbox), 0)

        self.assertEqual(len(mail.outbox), 2)

    @override_settings(
        NOTIFICATION_ADAPTERS=[
            "apps.notifications.adapters.email.FakeEmailNotificationAdapter",
            "invalid.path.to.Adapter",
        ]
    )
    def test_dynamic_adapter_loading_and_error_handling(self):
        """Verifica que se ignore rutas inválidas (loggeando error)."""
        # Limpiamos el cache de adaptadores al instanciar uno nuevo
        with self.assertLogs("apps.notifications.services", level="ERROR") as cm:
            service = NotificationService()
            self.assertEqual(len(service.adapters), 1)
            self.assertIsInstance(service.adapters[0], FakeEmailNotificationAdapter)
            self.assertIn("Could not load notification adapter", cm.output[0])

    def test_adapter_failure_handling(self):
        """Verifica que si un adaptador falla, el servicio retorna False para ese canal."""
        with patch.object(FakeEmailNotificationAdapter, "send", return_value=False):
            results = self.service.notify(
                recipient="test@example.com",
                subject="Failure test",
                message="Test",
                use_transaction=False,
            )
            self.assertFalse(results["fake_email"])
            self.assertTrue(results["email"])  # El otro debería seguir funcionando
