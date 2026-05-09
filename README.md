# Información

## Software Stack

- **Backend:** Django 6
- **Frontend CSS:** Tailwind CSS
- **Frontend Interactivity:** HTMX (para AJAX)
- **Frontend State/UI:** Alpine.js (interacciones _client-side_)
- **Base de datos:** PostgreSQL (falta configurar aún)

## Estructura del proyecto

- `pyproject.toml`: configuración del proyecto que utiliza `uv` para determinar la versión de python y las dependencias.
- `GYMFlow/`: Tiene la configuración del proyecto y las URL que apuntan a vistas.
  - `settings.py`: tiene toda la configuración del proyecto django.
  - `urls.py`: mapea vistas de django a urls.
- `static/`: Assets estáticos como css, js. Se sirve como están allí.
  - `base.html`: Las librerías JS (HTMX, Alpine.js, Tailwind) se cargan vía CDN aquí. Podríamos considerar incluirlas de forma estática o utilizar un bundler.
  - `partials`: Los partials de Django son bloques de codigo reutilizables. Permiten utilizar componentes HTML pasando parámetros desde otros archivos HTML. Parecido a React.

Módulos (Django Apps):

- `users/`: Módulo de autenticación y gestión de usuarios. Registros, asignación de roles y desarrollo del MFA para administradores.
- `classes/`: Módulo de gestión de clases e inscripciones. Configuración de las disciplinas, con sus horarios, profesores y lista de espera. Control de apertura/cierre de inscripciones según el calendario.
- `payments/`: Módulo de gestion de cobros. Integración con MercadoPago para cobros. Gestión de los créditos por cancelaciones anticipadas y registro de pagos en efectivo en recepción.
- `attendance/`: Módulo de asistencia. Generación/lectura de códigos QR y carga de constancias de tutores para menores de edad.
- `reports/`: Módulo de panel de administrador para visualizar los ingresos, cancelaciones, la concurrencia y más.
- `notifications/` Módulo de notificaciones. Envío de correos para la confirmación de cupos y recordatorios de clases.

## Esquema de la base de datos

En la implementación el esquema se encuentra distribuido en el archivo `models.py` del módulo que corresponda. Django viene con un [ORM](https://en.wikipedia.org/wiki/Object%E2%80%93relational_mapping) y realiza las migraciones a nuestra BD Postgres, de ser necesario ver [Django migrations](https://docs.djangoproject.com/en/6.0/topics/migrations/).

```mermaid
erDiagram
    USUARIO {
        int id PK
        string rol "CLIENTE, EMPLEADO, ADMIN"
        string nombre
        string apellido
        string dni
        string email
        date fecha_nacimiento
        string telefono_emergencia
        string url_constancia_tutor
        string estado_constancia "PENDIENTE, APROBADA, RECHAZADA"
    }
    SEDE {
        int id PK
        string nombre
        string direccion
    }
    SALA {
        int id PK
        int sede_id FK
        string nombre
        int capacidad
    }
    PROFESOR {
        int id PK
        string nombre
        string apellido
    }
    PERIODO_COBRO {
        int id PK
        string nombre
        date fecha_inicio_periodo
        date fecha_fin_periodo
        date apertura_abonados
        date apertura_general
    }
    DISCIPLINA {
        int id PK
        string nombre
        string descripcion
    }
    PRECIO_DISCIPLINA {
        int id PK
        int disciplina_id FK
        int periodo_id FK
        decimal monto
    }
    CLASE {
        int id PK
        int disciplina_id FK
        int sala_id FK
        int profesor_id FK
        datetime fecha_hora_inicio
        int duracion_minutos
        int cupo_maximo
        string estado
    }
    INSCRIPCION {
        int id PK
        int usuario_id FK
        int clase_id FK
        int periodo_id FK
        datetime fecha_registro
        string estado "ESPERA, RESERVADA, PENDIENTE_PAGO, CANCELADA"
    }
    ASISTENCIA {
        int id PK
        int inscripcion_id FK
        datetime fecha_hora_ingreso
        string metodo "QR, MANUAL"
        int registrado_por_id FK "Nullable (Empleado)"
    }
    PAGO {
        int id PK
        int usuario_id FK
        int periodo_id FK
        decimal monto
        datetime fecha_pago
        string metodo
        string tipo "MEMBRESIA, SENA, SALDO, CLASE_INDIVIDUAL"
        string estado "PENDIENTE, COMPLETADO, REEMBOLSADO"
    }
    CREDITO {
        int id PK
        int usuario_id FK
        int periodo_id FK
        int disciplina_id FK
        int cantidad
        string estado "DISPONIBLE, UTILIZADO"
    }

    PAGO_INSCRIPCION {
        int id PK
        int pago_id FK
        int inscripcion_id FK
        decimal monto_aplicado
    }

    PAGO ||--o{ PAGO_INSCRIPCION : "detalla"
    INSCRIPCION ||--o{ PAGO_INSCRIPCION : "es cubierta por"

    SEDE ||--o{ CLASE : "alberga"
    PROFESOR ||--o{ CLASE : "dicta"
    PERIODO_COBRO ||--o{ INSCRIPCION : "agrupa"
    PERIODO_COBRO ||---o{ SALA : "contiene"
    SALA ||-o{ PRECIO_DISCIPLINA : "define tarifas"
    PERIODO_COBRO ||--o{ PAGO : "registra recaudación"
    PERIODO_COBRO ||--o{ CREDITO : "limita validez"
    USUARIO ||--o{ INSCRIPCION : "realiza"
    USUARIO ||--o{ ASISTENCIA : "valida ingreso"
    USUARIO ||--o{ CREDITO : "obtiene"
    DISCIPLINA ||--o{ PRECIO_DISCIPLINA : "tiene costo"
    DISCIPLINA ||--o{ CLASE : "se dicta"
    CLASE ||--o{ INSCRIPCION : "recibe"
    INSCRIPCION ||--o| ASISTENCIA : "genera"
```

# Configuración del entorno de desarrollo

## Pre-requisitos

Para desarrollo utilizamos **docker**, con Python 3.14 y el gestor de paquetes uv. Especificado en `docker-compose.yml` y Dockerfile. Solo necesitás tener docker y docker-compose instalado.

Si preferís correr el backend localmente sin Docker podés, mirá [instalar uv](https://github.com/astral-sh/uv). Pero aún deberías conectarte a la base de datos PostgreSQL para poder ejecutar las migraciones y el servidor de Django.

## Desarrollo con docker (recomendado)

Esta es la forma más sencilla de levantar el proyecto. Incluye el servidor de Django con _live reload_ (*gymflow_web*), la base de datos PostgreSQL (*gymflow_db*) y pgAdmin (*gymflow_pgadmin*) para inspeccionar la BD. Los tres contenedores comparten la misma red (*gymflow_network*) para comunicarse entre sí.

1.  Para configurar las variables de entorno, copiá el archivo de ejemplo `.env.example` en `.env`, y modificalo:

    ```bash
    cp .env.example .env
    ```

1.  Para levantar el entorno ejecutá:

    ```bash
    docker compose up
    ```

1.  Para acceder:
    - App: [http://localhost:8000](http://localhost:8000)
    - pgAdmin: [http://localhost:5050](http://localhost:5050)

## Desarrollo local (con `uv`)

Si preferís no usar Docker para el servidor de Django:

1.  Levantar solo la base de datos y pgadmin:

    ```bash
    docker compose up -d db pgadmin
    ```

2.  Sincronizá las dependencias:

    ```bash
    uv sync
    ```

3.  Configurá el `.env`, y asegurate de que que esta variable se vea asi `POSTGRES_HOST=localhost`.

4.  Corré las migraciones y finalmente el servidor:

    ```bash
    uv run python manage.py migrate
    uv run python manage.py runserver
    ```

## Comandos útiles

El prefijo `uv run` es necesario para ejecutar los comandos dentro del entorno virtual. Si no estás utilizando docker, el prefijo `docker exec -it gymflow_web` no es necesario.

- Crear superusuario:

	```bash
	docker exec -it gymflow_web uv run python manage.py createsuperuser
  ```

- Hacer nuevas migraciones:

	```bash
	docker exec -it gymflow_web uv run python manage.py makemigrations
	```
  
- Ver logs:

  ```bash
  docker compose logs -f web
  ```

- Usar un shell dentro del container de Django:

	```bash
  docker exec -it gymflow_web uv run python manage.py shell
  ```

-  Al añadir o quitar alguna dependencia en `pyproject.toml`, al cambiar el `Dockerfile` o scripts de configuración en `docker/`, o si algo se rompe y querés limpiar el entorno, agregá el flag `--build` a `docker compose up`:

	```bash
	docker compose up --build
	```

-  Detener el entorno:

	```bash
	docker compose down
	```
