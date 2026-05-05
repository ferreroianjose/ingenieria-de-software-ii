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


# Setup

## Pre-requisitos

Para este proyecto usamos **uv**. Es un gestor de paquetes y entornos de Python escrito que reemplaza a `pip` y `venv`. Es mucho más rápido y simple.

Si no lo tenés, instalalo globalmente:

```bash
pip install uv
```

O revisá la documentacion: [https://github.com/astral-sh/uv](https://github.com/astral-sh/uv)

## Primera vez

1. Cloná el repositorio y entrá a la carpeta

1. Sincronizá el proyecto. Esto crea el entorno virtual y descarga todas las dependencias en las versiones correctas

  ```
  uv sync
  ```

## Correr

1. Para levantar el servidor de desarrollo ejecutá:

	```bash
	uv run python manage.py runserver
	```

1. Accedé por el navegador a [http://127.0.0.1:8000](http://127.0.0.1:8000).
