# Guía de Instalación y Comandos

## Pre-requisitos

Para desarrollo utilizamos **docker**, con Python 3.14 y el gestor de paquetes uv. Especificado en `docker-compose.yml` y Dockerfile. Solo necesitás tener docker y docker-compose instalado.

Si preferís correr el backend localmente sin Docker podés, mirá [instalar uv](https://github.com/astral-sh/uv). Pero aún deberías conectarte a la base de datos PostgreSQL para poder ejecutar las migraciones y el servidor de Django.

## Desarrollo con docker (recomendado)

Esta es la forma más sencilla de levantar el proyecto. Incluye el servidor de Django con *live reload* (*gymflow_web*), la base de datos PostgreSQL (*gymflow_db*) y Django Q (*gymflow_qcluster*) para ejecución asíncrona. Los contenedores comparten la misma red (*gymflow_network*) para comunicarse entre sí.

1. Para configurar las variables de entorno, copiá el archivo de ejemplo `.env.example` en `.env`, y modificalo:
  ```bash
    cp .env.example .env
  ```
2. Para levantar el entorno ejecutá:
  ```bash
    docker compose up
  ```
3. Para acceder:
  - App: [http://localhost:8000](http://localhost:8000)

## Desarrollo local (con `uv`)

Si preferís no usar Docker para el servidor de Django:

1. Levantar solo la base de datos:
  ```bash
    docker compose up -d db
  ```
2. Sincronizá las dependencias:
  ```bash
    uv sync
  ```
3. Configurá el `.env`, y asegurate de que que esta variable se vea asi `POSTGRES_HOST=localhost`.
4. Corré las migraciones y finalmente el servidor:
  ```bash
    uv run python manage.py migrate
    uv run python manage.py runserver
  ```

## Comandos útiles

El prefijo `uv run` es necesario para ejecutar los comandos dentro del entorno virtual. Si no estás utilizando docker, el prefijo `docker exec -it gymflow_web` no es necesario.

- Crear superusuario:
- Hacer nuevas migraciones:
- Ver logs:
  ```bash
  docker compose logs -f web
  ```
- Usar un shell dentro del container de Django:

## Carga de datos iniciales

Los datos iniciales (como usuarios por defecto) se cargan mediante *fixtures* en el directorio `fixtures/` de cada módulo (Django App). Por ejemplo, en `apps/users/fixtures/initial_users.json`.

E.g. en el módulo `users`: El comando `load_initial_users` carga usuarios desde el fixture. El comando se ejecuta automáticamente después de las migraciones en `docker/backend/docker-entrypoint.sh`, tras verificar si `DJANGO_DEBUG` está activado.

Si no usas docker para correrlo, después de `uv run python manage.py migrate`, ejecutá manualmente (en este orden):

```bash
uv run python manage.py load_initial_users
uv run python manage.py load_initial_classes
uv run python manage.py load_initial_payments
```

El módulo `payments` carga el período de cobro vigente, precios por disciplina, inscripciones de ejemplo y pagos de demostración.

Para agregar datos iniciales en otro módulo (ej. `classes`):

1. Creá un fixture en `apps/classes/fixtures/initial_classes.json`.
2. Creá un comando en `apps/classes/management/commands/load_initial_classes.py` (copiá el patrón de `users`, adaptando para tus modelos y campos únicos).
3. Agregá una línea en `docker/backend/docker-entrypoint.sh` (después de las dependencias que necesite tu módulo).

De esta forma cada módulo maneja la carga de sus propios datos iniciales de forma idempotente (verifica si ya existen antes de crear, para no duplicar). Así, ese script solo correría durante el desarrollo, y evitamos problemas de migraciones 🥴.

## Pagos de prueba (Mercado Pago)

Referencia: [Compras de prueba – Checkout Pro](https://www.mercadopago.com.ar/developers/es/docs/checkout-pro/integration-test/test-purchases)

1. Configurar `.env`

  Copiá en `.env` las **Credenciales de prueba** de tu app:

  - [Tus integraciones](https://www.mercadopago.com.ar/developers/panel/app) → tu aplicación → **Credenciales de prueba**
  - `MERCADO_PAGO_PUBLIC_KEY`
  - `MERCADO_PAGO_ACCESS_TOKEN`

  Reiniciá el contenedor: `docker compose restart web`

2. Anotar el comprador de prueba

  En el mismo panel: **Cuentas de prueba** → **Comprador**. Guardá:

  - **Usuario** (ej. `TESTUSER…`; es el login, no un email)
  - **Contraseña**
  - **User ID** (por si piden código: usá los últimos 6 dígitos)

  Es más fácil usar esto, permite seleccionar la tarjeta de prueba, y no tener que ingresar cada dato de esta manualmente.

3. Reservar y abrir el checkout

  USÁ MODO INCOGNITO U OTRO NAVEGADOR. No ingreses con tu cuenta de MP.

  1. Entrá a GYMFlow como cliente.
  2. Reservá una clase.
  3. Seguí el flujo hasta **Pagar**. La app te lleva a `sandbox.mercadopago.com.ar/checkout/...`.

4. Iniciar sesión en Mercado Pago

  En el checkout, elegí **Ingresar** e ingresá el **Usuario** y **Contraseña** del comprador de prueba (paso 2).

5. Pagar con tarjeta de prueba

  Elegí alguna de las tarjetas, y pagá con el código de seguridad 123. Sino, ingresá manualmente sus valores para controlar el resultado del pago mediante el nombre del titular. [Fijate acá](https://www.mercadopago.com.ar/developers/es/docs/your-integrations/test/cards).
