# Información

## Software Stack

- **Backend:** Django 6
- **Frontend CSS:** Tailwind CSS
- **Frontend Interactivity:** HTMX (para AJAX)
- **Frontend State/UI:** Alpine.js (interacciones *client-side*)
- **Base de datos:** PostgreSQL (falta configurar aún)


## Estructura del proyecto

* `pyproject.toml`: configuración del proyecto que utiliza `uv` para determinar la versión de python y las dependencias. 
* `GYMFlow/`: Tiene la configuración del proyecto y las URL que apuntan a vistas.
  * `settings.py`: tiene toda la configuración del proyecto django.
  * `urls.py`: mapea vistas de django a urls.
* `static/`: Assets estáticos como css, js. Se sirve como están allí.
	* `base.html`: Las librerías JS (HTMX, Alpine.js, Tailwind) se cargan vía CDN aquí. Podríamos considerar incluirlas de forma estática o utilizar un bundler. 
	* `partials`: Los partials de Django son bloques de codigo reutilizables. Permiten utilizar componentes HTML pasando parámetros desde otros archivos HTML. Parecido a React.

Módulos (Django Apps):

* `users/`: Módulo de autenticación y gestión de usuarios. Registros, asignación de roles y desarrollo del MFA para administradores.
* `classes/`: Módulo de gestión de clases e inscripciones. Configuración de las disciplinas, con sus horarios, profesores y lista de espera. Control de apertura/cierre de inscripciones según el calendario.
* `payments/`: Módulo de gestion de cobros. Integración con MercadoPago para cobros. Gestión de los créditos por cancelaciones anticipadas y registro de pagos en efectivo en recepción.
* `attendance/`: Módulo de asistencia. Generación/lectura de códigos QR y carga de constancias de tutores para menores de edad.
* `reports/`: Módulo de panel de administrador para visualizar los ingresos, cancelaciones, la concurrencia y más.
* `notifications/` Módulo de notificaciones. Envío de correos para la confirmación de cupos y recordatorios de clases.

# Setup

## Pre-requisitos

Para este proyecto usamos **uv**. Es un gestor de paquetes y entornos de Python escrito que reemplaza a `pip` y `venv`. Es mucho más rápido y simple.

Si no lo tenés, instalalo globalmente:

```bash
pip install uv
```

O revisá la documentacion: [https://github.com/astral-sh/uv](https://github.com/astral-sh/uv)

Además, instalá docker y docker-compose.

## Primera vez

1. Cloná el repositorio y entrá a la carpeta

1. Sincronizá el proyecto. Esto crea el entorno virtual y descarga todas las dependencias en las versiones correctas

  ```
  uv sync
  ```

Para levantar el servidor de PostgreSQL:

1. Copiá el ejemplo de variables de entorno en `.env.example` como `.env`, ajustá si querés las credenciales.
2. Levantá el servidor de base de datos:

	```bash
	docker compose up -d --build
	uv run python manage.py makemigrations
	uv run python manage.py migrate
	uv run python manage.py createsuperuser # opcional
	```

## Correr

1. Asegurate que esté corriendo el servidor de base de datos con `docker ps`. Si no está corriendo y ya lo tenés configurado, `docker start gymflow_db`.
1. Para levantar el servidor de desarrollo ejecutá:

	```bash
	uv run python manage.py runserver
	```

1. Accedé por el navegador a [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Visualizar la base de datos

En el docker compose tenemos configurado `pgAdmin` para visualizar la base de datos. Accedé a [http://localhost:5050](http://localhost:5050) y logueate con las credenciales que configuraste en el `.env` o el superusuario que hayas creado.
