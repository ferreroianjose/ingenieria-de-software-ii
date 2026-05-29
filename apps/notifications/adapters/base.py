from abc import ABC, abstractmethod
from typing import Any, Union

from django.db import transaction


class NotificationAdapter(ABC):
    @property
    @abstractmethod
    def slug(self) -> str:
        """Identificador único del adaptador (ej: 'email', 'sms')."""
        pass

    @property
    def default_async(self) -> bool:
        """
        Define si el adaptador prefiere ser asíncrono por defecto.
        """
        return True

    def send(self, recipient: Any, subject: str, message: str, use_transaction: bool = None, **kwargs: Any) -> bool:
        """
        Punto de entrada principal.

        use_transaction=True: envía al hacer commit de la transacción DB actual (síncrono).
        use_transaction=False: envío síncrono inmediato.
        use_transaction=None: usa default_async (django-q si True).
        """
        if use_transaction is True:
            if not self.get_recipient_address(recipient):
                return False

            def _send_after_commit():
                self._perform_send(recipient, subject, message, **kwargs)

            transaction.on_commit(_send_after_commit)
            return True

        should_async = self.default_async if use_transaction is None else False

        if should_async:
            # Resolvemos el contacto para que el dato que viaje al worker sea serializable
            contact = self.get_recipient_address(recipient)
            if not contact:
                return False

            from django_q.tasks import async_task
            task_id = async_task(
                "apps.notifications.tasks.send_notification_task",
                self.slug,
                contact,
                subject,
                message,
                group=self.slug,  # Identificamos el grupo de la tarea con el slug del adaptador
                **kwargs
            )
            # Retornamos el ID de la tarea para seguimiento
            return task_id
        
        # Si no es asíncrono, procedemos a la implementación física
        return self._perform_send(recipient, subject, message, **kwargs)

    @abstractmethod
    def _perform_send(self, recipient: Any, subject: str, message: str, **kwargs: Any) -> bool:
        """
        Implementación física del envío (SMTP, API, etc.).
        """
        pass

    def get_recipient_address(self, recipient: Any) -> str:
        """
        Extrae la dirección de contacto del destinatario según el slug del adaptador.
        """
        if hasattr(recipient, "get_notification_contact"):
            return recipient.get_notification_contact(self.slug)
        return str(recipient)
