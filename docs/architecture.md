# Arquitectura

## Software Stack

- **Backend:** Django 6
- **Task Queue:** Django Q
- **Frontend CSS:** Tailwind CSS
- **Frontend Interactivity:** HTMX
- **Frontend State/UI:** Alpine.js
- **Base de datos:** PostgreSQL

## Estructura del proyecto

- `pyproject.toml`: Configuración del proyecto que utiliza `uv` para determinar la versión de python y las dependencias.
- `GYMFlow/`: Tiene la configuración del proyecto y las URL que apuntan a vistas.
  - `settings.py`: Tiene toda la configuración del proyecto django.
  - `urls.py`: Mapea vistas de django a urls.
- `static/`: Assets estáticos como css, js. Se sirve como están allí.
  - `base.html`: Las librerías JS (HTMX, Alpine.js, Tailwind) se cargan vía CDN aquí.
  - `partials`: Los partials de Django son bloques de codigo reutilizables. Permiten utilizar componentes HTML pasando parámetros desde otros archivos HTML. Parecido a React.
- `templates/`: Los templates de Django son los archivos HTML que se renderizan en las vistas.

Los módulos (Django Apps) se encuentran en el directorio `apps/`:

- `users/`: Módulo de autenticación y gestión de usuarios. Registros, asignación de roles y desarrollo del MFA para administradores.
- `classes/`: Módulo de gestión de clases e inscripciones. Configuración de las disciplinas, con sus horarios, profesores y lista de espera. Control de apertura/cierre de inscripciones según el calendario.
- `payments/`: Módulo de gestion de cobros. Integración con MercadoPago para cobros. Gestión de los créditos por cancelaciones anticipadas y registro de pagos en efectivo en recepción.
- `attendance/`: Módulo de asistencia. Generación/lectura de códigos QR y carga de constancias de tutores para menores de edad.
- `reports/`: Módulo de panel de administrador para visualizar los ingresos, cancelaciones, la concurrencia y más.
- `notifications/` Módulo de notificaciones. Envío de correos para la confirmación de cupos y recordatorios de clases.

Para cada módulo, dentro de `templates/` y un directorio de su propio nombre, se encuentran los archivos HTML que se renderizan en las vistas.

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
        file constancia_tutor
        string estado_constancia "PENDIENTE, APROBADA, RECHAZADA"
    }
    SEDE {
        int id PK
        string nombre "unique"
        string direccion
        datetime created_at
        datetime updated_at
    }
    SALA {
        int id PK
        int sede_id FK
        string nombre "unique por sede"
        int capacidad
        datetime created_at
        datetime updated_at
    }
    PROFESOR {
        int id PK
        string nombre
        string apellido "unique (nombre, apellido)"
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
        string nombre "unique"
        string descripcion "opcional"
        datetime created_at
        datetime updated_at
    }
    PRECIO_DISCIPLINA {
        int id PK
        int disciplina_id FK
        int periodo_id FK
        decimal monto
    }
    CLASE {
        int id PK
        int disciplina_id FK "nullable, PROTECT"
        int sala_id FK "nullable, PROTECT"
        int profesor_id FK "PROTECT"
        int dia_semana "0=Lun, 1=Mar, ..., 6=Dom"
        time hora_inicio "nullable"
        duration duracion
        int cupo_maximo
        string estado "disponible, pausada"
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
    SEDE ||--o{ SALA : "contiene"
    SALA ||--o{ CLASE : "alberga"
    PROFESOR ||--o{ CLASE : "dicta"
    PERIODO_COBRO ||--o{ INSCRIPCION : "agrupa"
    PERIODO_COBRO ||--o{ PRECIO_DISCIPLINA : "define tarifas"
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
