# Información general

Este proyecto fue desarrollado en el marco de la asignatura **Ingeniería de Software II** de la Facultad de Informática de la **Universidad Nacional de La Plata (UNLP)**.

**GYMFlow** es un sistema integral de gestión diseñado para el centro de actividades físicas *Siempre GYM*.

## Quick Start

Para levantar el entorno de desarrollo rápidamente:

1.  **Configurá las variables de entorno:**
    ```bash
    cp .env.example .env
    ```
2.  **Iniciá los contenedores:**
    ```bash
    docker compose up
    ```
3.  **Accedé al sistema:** [http://localhost:8000](http://localhost:8000)

## Documentación

Para profundizar en la implementación consultá:

* [Arquitectura](docs/architecture.md): Stack tecnológico, organización del proyecto y modelos de datos.
* [Guía de Instalación y comandos útiles](docs/setup.md): Requisitos previos, uso de `uv`, compilación de Tailwind, migraciones y carga de datos iniciales.
* [Módulo de Notificaciones](docs/notifications.md): Documentación relevante sobre el envío de alertas.
