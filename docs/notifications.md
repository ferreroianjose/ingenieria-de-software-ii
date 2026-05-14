# Notificaciones

El módulo de notificaciones (`apps/notifications`) utiliza el patrón **Adapter** para posibilitar el envío a través de diferentes canales a futuro.

## Configuración

Los servicios disponibles se configuran en `GYMFLOW/settings.py`. En desarrollo se incluye automáticamente el adaptador de consola.

```python
NOTIFICATION_ADAPTERS = [
    "apps.notifications.adapters.email.EmailNotificationAdapter",
]
```

* `FakeEmailNotificationAdapter`: Correos falsos. Se imprimen en la consola de la terminal.
* `EmailNotificationAdapter`: Envío real vía SMTP utilizando los backends de Django.

Para configurar el envío real, se utilizan estas variables en el `.env`:

- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`: Configuración del servidor SMTP.
- `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`: Credenciales de autenticación.
- `DEFAULT_FROM_EMAIL`: El remitente (ej: `Siempre GYM <noreply@siempregym.com>`).

## Uso del servicio

Para enviar notificaciones, se utiliza un patron singleton en `/apps/notifications/services.py`:

```python
from apps.notifications.services import notification_service

# Envío a todos los canales
notification_service.notify(
    recipient=user_instance,
    subject="Asunto",
    message="Mensaje"
)

# Envío a un canal específico
notification_service.notify(
    recipient="admin@gymflow.com",
    subject="Alerta",
    message="Error en el sistema",
    adapter_slug="fake_email"
)
```
