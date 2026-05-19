# Notificaciones

El módulo de notificaciones (`apps/notifications`) utiliza el patrón **Adapter** para posibilitar el envío a través de diferentes canales a futuro, y **Django Q2** para el procesamiento en segundo plano.

## Configuración

Los servicios disponibles se configuran en `GYMFLOW/settings.py`. En desarrollo se incluye automáticamente el adaptador de consola.

```python
NOTIFICATION_ADAPTERS = [
    "apps.notifications.adapters.email.EmailNotificationAdapter",
]
```

## Uso del servicio

El sistema utiliza **Django Q2** para evitar bloquear el servidor durante el envío de correos.

```python
from apps.notifications.services import notification_service

# Envío asíncrono (recomendado)
notification_service.notify(
    recipient=user_instance,
    subject="Asunto",
    message="Mensaje"
)

# Envío síncrono
notification_service.notify(
    recipient="admin@gymflow.com",
    subject="Alerta",
    message="Error en el sistema",
    use_transaction=False
)
```
