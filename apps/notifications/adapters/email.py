import logging
from typing import Any

from django.conf import settings
from django.core.mail import get_connection, EmailMultiAlternatives

from .base import NotificationAdapter

logger = logging.getLogger(__name__)


class BaseEmailAdapter(NotificationAdapter):
    """Base class for Django-based email adapters."""
    backend = None

    def send(self, recipient: Any, subject: str, message: str, **kwargs: Any) -> bool:
        recipient_address = self.get_recipient_address(recipient)
        try:
            from_email = kwargs.get("from_email", settings.DEFAULT_FROM_EMAIL)
            html_message = kwargs.get("html_message")
            
            # Obtenemos la conexión específica para este adaptador
            connection = get_connection(self.backend)
            
            email = EmailMultiAlternatives(
                subject,
                message,
                from_email,
                [recipient_address],
                connection=connection
            )
            
            if html_message:
                email.attach_alternative(html_message, "text/html")
            
            email.send(fail_silently=False)
            return True
        except Exception as e:
            logger.error(f"Failed to send email ({self.slug}) to {recipient_address}: {str(e)}")
            return False


class EmailNotificationAdapter(BaseEmailAdapter):
    """Envía correos reales usando el backend SMTP de Django."""
    @property
    def slug(self) -> str:
        return "email"
    
    backend = "django.core.mail.backends.smtp.EmailBackend"


class FakeEmailNotificationAdapter(BaseEmailAdapter):
    """'Envía' correos a la consola usando el backend de consola de Django."""
    @property
    def slug(self) -> str:
        return "fake_email"
    
    backend = "django.core.mail.backends.console.EmailBackend"
