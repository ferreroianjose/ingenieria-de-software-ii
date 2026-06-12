# Core App

Esta aplicación (`apps/core/`) tiene como propósito alojar código, utilidades y configuraciones que son globales al sistema GYMFlow y que no pertenecen estrictamente a ningún módulo de negocio particular.

## Contenido

- **Vistas globales (`views.py`)**: Vistas compartidas como páginas estáticas (Index, FAQ, Terms of Service).
- **Formularios genéricos (`forms.py`)**: Clases de formularios base o formularios sin un módulo específico.
- **Utilidades de UI/Acceso (`access.py`, `page_chrome.py`)**: Decoradores y helpers para validaciones de rol, estados de autenticación y utilidades visuales (como alertas o notificaciones Toast).
- **Template Context Processors (`context_processors.py`)**: Proveen variables globales (como los links de navegación principal) para todos los templates.
- **Management Commands (`management/commands/`)**: Comandos genéricos de Django, como el script unificado de inicialización de base de datos (`seed.py`).

Esta separación permite mantener la carpeta principal de configuración del proyecto (`gymflow/`) únicamente dedicada al enrutamiento general y configuraciones de entorno.
