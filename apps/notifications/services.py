import logging
from typing import Any, Dict, List, Union

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils.module_loading import import_string

from .adapters.base import NotificationAdapter

User = get_user_model()
logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self, adapters: List[NotificationAdapter] = None):
        if adapters is not None:
            self._adapters = {a.slug: a for a in adapters}
        else:
            self._adapters = self._load_adapters_from_settings()

    def _load_adapters_from_settings(self) -> Dict[str, NotificationAdapter]:
        adapters_map = {}
        adapter_paths = getattr(settings, "NOTIFICATION_ADAPTERS", [])
        for path in adapter_paths:
            try:
                adapter_class = import_string(path)
                instance = adapter_class()
                adapters_map[instance.slug] = instance
            except ImportError as e:
                logger.error(f"Could not load notification adapter {path}: {e}")
        return adapters_map

    @property
    def adapters(self) -> List[NotificationAdapter]:
        return list(self._adapters.values())

    def notify(
        self, 
        recipient: Union[str, User], 
        subject: str, 
        message: str, 
        use_transaction: bool = None,
        adapter_slug: str = None,
        **kwargs: Any
    ) -> Dict[str, Any]:
        """
        Notifica a través de los canales. Permite filtrar por slug para envíos específicos.
        """
        results = {}
        # Seleccionamos adaptadores
        if adapter_slug:
            adapter = self.get_adapter(adapter_slug)
            adapters_to_use = [adapter] if adapter else []
        else:
            adapters_to_use = self._adapters.values()

        for adapter in adapters_to_use:
            results[adapter.slug] = adapter.send(
                recipient, subject, message, use_transaction=use_transaction, **kwargs
            )
        return results

    def get_adapter(self, slug: str) -> Union[NotificationAdapter, None]:
        return self._adapters.get(slug)


# Singleton para facilitar el acceso global
notification_service = NotificationService()
