import logging
from typing import Any, Dict, List, Union

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.module_loading import import_string

from .adapters.base import NotificationAdapter

User = get_user_model()
logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, adapters: List[NotificationAdapter] = None):
        if adapters is not None:
            self.adapters = adapters
        else:
            self.adapters = self._load_adapters_from_settings()

    def _load_adapters_from_settings(self) -> List[NotificationAdapter]:
        adapters = []
        adapter_paths = getattr(settings, "NOTIFICATION_ADAPTERS", [])
        
        for path in adapter_paths:
            try:
                adapter_class = import_string(path)
                adapters.append(adapter_class())
            except ImportError as e:
                logger.error(f"Could not load notification adapter {path}: {e}")
        
        return adapters

    def notify(
        self, 
        recipient: Union[str, User], 
        subject: str, 
        message: str, 
        use_transaction: bool = True,
        adapter_slug: str = None,
        **kwargs: Any
    ) -> Dict[str, bool]:
        """
        Envía notificaciones a través de los adaptadores configurados.
        
        :param use_transaction: Si es True, pospone el envío hasta que la DB confirme la transacción.
        :param adapter_slug: Si se provee, solo envía a través de ese adaptador específico.
        :return: Diccionario con el resultado por cada adaptador {slug: success}
        """
        if use_transaction:
            # Envío "asíncrono" (pospuesto al commit)
            transaction.on_commit(
                lambda: self._execute_send(recipient, subject, message, adapter_slug, **kwargs)
            )
            # Retornamos un estado pendiente
            adapters_to_report = [a for a in self.adapters if not adapter_slug or a.slug == adapter_slug]
            return {adapter.slug: True for adapter in adapters_to_report}
        
        return self._execute_send(recipient, subject, message, adapter_slug, **kwargs)

    def _execute_send(
        self, 
        recipient: Union[str, User], 
        subject: str, 
        message: str, 
        adapter_slug: str = None,
        **kwargs: Any
    ) -> Dict[str, bool]:
        results = {}
        for adapter in self.adapters:
            if adapter_slug and adapter.slug != adapter_slug:
                continue
            success = adapter.send(recipient, subject, message, **kwargs)
            results[adapter.slug] = success
        return results


# Singleton para facilitar el acceso global
notification_service = NotificationService()
