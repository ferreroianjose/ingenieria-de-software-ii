from abc import ABC, abstractmethod
from typing import Any, Union


class NotificationAdapter(ABC):
    @property
    @abstractmethod
    def slug(self) -> str:
        """Identificador único del adaptador (ej: 'email', 'sms')."""
        pass

    @abstractmethod
    def send(self, recipient: Any, subject: str, message: str, **kwargs: Any) -> bool:
        """
        Envía una notificación.
        :param recipient: Instancia que implementa get_notification_contact o string.
        :param subject: Asunto de la notificación.
        :param message: Cuerpo de la notificación.
        :param kwargs: Argumentos adicionales para adaptadores específicos.
        :return: True si se envió correctamente, False en caso contrario.
        """
        pass

    def get_recipient_address(self, recipient: Any) -> str:
        """
        Extrae la dirección de contacto del destinatario según el slug del adaptador.
        """
        if hasattr(recipient, "get_notification_contact"):
            return recipient.get_notification_contact(self.slug)
        return str(recipient)

    @property
    def name(self) -> str:
        """Retorna el nombre de la clase del adaptador."""
        return self.__class__.__name__
