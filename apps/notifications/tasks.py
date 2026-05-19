import logging
from typing import Any

from .services import notification_service

logger = logging.getLogger(__name__)

def send_notification_task(
    adapter_slug: str,
    recipient: str, 
    subject: str, 
    message: str, 
    **kwargs: Any
) -> bool:
    """
    Tarea de fondo ejecutada por el Worker para asegurar el paralelismo.
    Invoca directamente la implementación física del adaptador para realizar
    el envío real.
    """
    adapter = notification_service.get_adapter(adapter_slug)
    if not adapter:
        logger.error(f"Worker Error: Adaptador con slug '{adapter_slug}' no encontrado.")
        return False

    logger.info(f"Worker procesando implementación física de {adapter_slug} para {recipient}")
    
    return adapter._perform_send(recipient, subject, message, **kwargs)
