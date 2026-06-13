"""
manage.py seed
==============
Pobla la base de datos con datos de desarrollo/demo.
Todos los datos se definen aquí en Python puro — sin fixtures JSON.

Uso:
    uv run python manage.py seed            # carga todo
    uv run python manage.py seed --reset    # borra datos previos y vuelve a sembrar

El comando es idempotente por defecto: si los datos ya existen los omite.
Con --reset limpia primero y siembra desde cero.

Orden de carga (respeta dependencias entre modelos):
    1. Usuarios (admins, empleados, clientes)
    2. Sedes, Salas, Disciplinas, Profesores
    3. Clases
    4. Períodos de cobro (fechas RELATIVAS a hoy)
    5. Precios por disciplina/período
    6. Inscripciones de ejemplo
    7. Pagos de ejemplo
    8. Créditos de ejemplo
"""

from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.utils import timezone


# ---------------------------------------------------------------------------
# Datos de referencia
# ---------------------------------------------------------------------------

USUARIOS = [
    # — Administradores —
    {
        "email": "laura@siempregym.com",
        "raw_password": "laura123",
        "first_name": "Laura",
        "last_name": "Ibarra",
        "rol": "ADMIN",
        "is_superuser": True,
        "dni": "00000000",
        "fecha_nacimiento": date(1985, 3, 15),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "jose@siempregym.com",
        "raw_password": "jose123",
        "first_name": "José",
        "last_name": "Mckenzie",
        "rol": "ADMIN",
        "is_superuser": True,
        "dni": "00000001",
        "fecha_nacimiento": date(1988, 7, 22),
        "estado_constancia": "APROBADA",
    },
    # — Empleados —
    {
        "email": "empleado@siempregym.com",
        "raw_password": "empleado123",
        "first_name": "Empleado",
        "last_name": "Uno",
        "rol": "EMPLEADO",
        "dni": "11111111",
        "fecha_nacimiento": date(1995, 11, 2),
        "estado_constancia": "APROBADA",
    },
    # — Clientes —
    {
        "email": "enrique@email.com",
        "raw_password": "enrique123",
        "first_name": "Enrique",
        "last_name": "Gonzales",
        "rol": "CLIENTE",
        "dni": "22222222",
        "fecha_nacimiento": date(2002, 5, 10),
        "telefono_emergencia": "3516789012",
        "estado_constancia": "APROBADA",
    },
    {
        "email": "guadalupe@email.com",
        "raw_password": "guadalupe123",
        "first_name": "Guadalupe",
        "last_name": "Figueroa",
        "rol": "CLIENTE",
        "dni": "22222223",
        "fecha_nacimiento": date(2005, 9, 30),
        "estado_constancia": "PENDIENTE",
    },
    {
        "email": "martin.lopez@mail.com",
        "raw_password": "cliente123",
        "first_name": "Martín",
        "last_name": "López",
        "rol": "CLIENTE",
        "dni": "30111222",
        "fecha_nacimiento": date(1992, 1, 18),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "sofia.ramirez@mail.com",
        "raw_password": "cliente123",
        "first_name": "Sofía",
        "last_name": "Ramírez",
        "rol": "CLIENTE",
        "dni": "30222333",
        "fecha_nacimiento": date(1998, 6, 25),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "diego.torres@mail.com",
        "raw_password": "cliente123",
        "first_name": "Diego",
        "last_name": "Torres",
        "rol": "CLIENTE",
        "dni": "30333444",
        "fecha_nacimiento": date(1989, 11, 3),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "valentina.morales@mail.com",
        "raw_password": "cliente123",
        "first_name": "Valentina",
        "last_name": "Morales",
        "rol": "CLIENTE",
        "dni": "30444555",
        "fecha_nacimiento": date(2007, 4, 12),
        "estado_constancia": "PENDIENTE",
    },
    {
        "email": "lucas.fernandez@mail.com",
        "raw_password": "cliente123",
        "first_name": "Lucas",
        "last_name": "Fernández",
        "rol": "CLIENTE",
        "dni": "30555666",
        "fecha_nacimiento": date(1995, 8, 30),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "camila.sosa@mail.com",
        "raw_password": "cliente123",
        "first_name": "Camila",
        "last_name": "Sosa",
        "rol": "CLIENTE",
        "dni": "30666777",
        "fecha_nacimiento": date(2001, 12, 7),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "tomas.acosta@mail.com",
        "raw_password": "cliente123",
        "first_name": "Tomás",
        "last_name": "Acosta",
        "rol": "CLIENTE",
        "dni": "30777888",
        "fecha_nacimiento": date(2008, 2, 14),
        "estado_constancia": "PENDIENTE",
    },
    {
        "email": "florencia.ruiz@mail.com",
        "raw_password": "cliente123",
        "first_name": "Florencia",
        "last_name": "Ruiz",
        "rol": "CLIENTE",
        "dni": "30888999",
        "fecha_nacimiento": date(1990, 9, 21),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "juan.perez@mail.com",
        "raw_password": "cliente123",
        "first_name": "Juan",
        "last_name": "Pérez",
        "rol": "CLIENTE",
        "dni": "30999000",
        "fecha_nacimiento": date(1987, 3, 9),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "mariana.gomez@mail.com",
        "raw_password": "cliente123",
        "first_name": "Mariana",
        "last_name": "Gómez",
        "rol": "CLIENTE",
        "dni": "31000111",
        "fecha_nacimiento": date(1996, 7, 16),
        "estado_constancia": "RECHAZADA",
    },
    {
        "email": "nicolas.herrera@mail.com",
        "raw_password": "cliente123",
        "first_name": "Nicolás",
        "last_name": "Herrera",
        "rol": "CLIENTE",
        "dni": "31111222",
        "fecha_nacimiento": date(1993, 10, 28),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "agustina.molina@mail.com",
        "raw_password": "cliente123",
        "first_name": "Agustina",
        "last_name": "Molina",
        "rol": "CLIENTE",
        "dni": "31222333",
        "fecha_nacimiento": date(2006, 5, 5),
        "estado_constancia": "PENDIENTE",
    },
    {
        "email": "facundo.castro@mail.com",
        "raw_password": "cliente123",
        "first_name": "Facundo",
        "last_name": "Castro",
        "rol": "CLIENTE",
        "dni": "31333444",
        "fecha_nacimiento": date(1991, 1, 31),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "paula.vega@mail.com",
        "raw_password": "cliente123",
        "first_name": "Paula",
        "last_name": "Vega",
        "rol": "CLIENTE",
        "dni": "31444555",
        "fecha_nacimiento": date(1999, 11, 19),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "santiago.ibarra@mail.com",
        "raw_password": "cliente123",
        "first_name": "Santiago",
        "last_name": "Ibarra",
        "rol": "CLIENTE",
        "dni": "31555666",
        "fecha_nacimiento": date(2004, 8, 8),
        "estado_constancia": "PENDIENTE",
    },
    {
        "email": "romina.silva@mail.com",
        "raw_password": "cliente123",
        "first_name": "Romina",
        "last_name": "Silva",
        "rol": "CLIENTE",
        "dni": "31666777",
        "fecha_nacimiento": date(1986, 4, 22),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "german.ortiz@mail.com",
        "raw_password": "cliente123",
        "first_name": "Germán",
        "last_name": "Ortiz",
        "rol": "CLIENTE",
        "dni": "31777888",
        "fecha_nacimiento": date(1994, 12, 11),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "carla.medina@mail.com",
        "raw_password": "cliente123",
        "first_name": "Carla",
        "last_name": "Medina",
        "rol": "CLIENTE",
        "dni": "31888999",
        "fecha_nacimiento": date(2009, 6, 1),
        "estado_constancia": "PENDIENTE",
    },
    {
        "email": "leandro.romero@mail.com",
        "raw_password": "cliente123",
        "first_name": "Leandro",
        "last_name": "Romero",
        "rol": "CLIENTE",
        "dni": "31999000",
        "fecha_nacimiento": date(1988, 2, 27),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "belen.navarro@mail.com",
        "raw_password": "cliente123",
        "first_name": "Belén",
        "last_name": "Navarro",
        "rol": "CLIENTE",
        "dni": "32000111",
        "fecha_nacimiento": date(1997, 9, 14),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "franco.mendez@mail.com",
        "raw_password": "cliente123",
        "first_name": "Franco",
        "last_name": "Méndez",
        "rol": "CLIENTE",
        "dni": "32111222",
        "fecha_nacimiento": date(2003, 3, 23),
        "estado_constancia": "RECHAZADA",
    },
    {
        "email": "juliana.campos@mail.com",
        "raw_password": "cliente123",
        "first_name": "Juliana",
        "last_name": "Campos",
        "rol": "CLIENTE",
        "dni": "32222333",
        "fecha_nacimiento": date(2000, 10, 6),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "maximiliano.suarez@mail.com",
        "raw_password": "cliente123",
        "first_name": "Maximiliano",
        "last_name": "Suárez",
        "rol": "CLIENTE",
        "dni": "32333444",
        "fecha_nacimiento": date(1992, 7, 29),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "melina.rios@mail.com",
        "raw_password": "cliente123",
        "first_name": "Melina",
        "last_name": "Ríos",
        "rol": "CLIENTE",
        "dni": "32444555",
        "fecha_nacimiento": date(2008, 11, 17),
        "estado_constancia": "PENDIENTE",
    },
    {
        "email": "andres.vargas@mail.com",
        "raw_password": "cliente123",
        "first_name": "Andrés",
        "last_name": "Vargas",
        "rol": "CLIENTE",
        "dni": "32555666",
        "fecha_nacimiento": date(1985, 12, 30),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "noelia.paredes@mail.com",
        "raw_password": "cliente123",
        "first_name": "Noelia",
        "last_name": "Paredes",
        "rol": "CLIENTE",
        "dni": "32666777",
        "fecha_nacimiento": date(1998, 2, 2),
        "estado_constancia": "APROBADA",
    },
    {
        "email": "cristian.benitez@mail.com",
        "raw_password": "cliente123",
        "first_name": "Cristian",
        "last_name": "Benítez",
        "rol": "CLIENTE",
        "dni": "32777888",
        "fecha_nacimiento": date(2006, 8, 19),
        "estado_constancia": "PENDIENTE",
    },
    {
        "email": "lorena.gimenez@mail.com",
        "raw_password": "cliente123",
        "first_name": "Lorena",
        "last_name": "Giménez",
        "rol": "CLIENTE",
        "dni": "32888999",
        "fecha_nacimiento": date(1991, 5, 24),
        "estado_constancia": "APROBADA",
    },
]

# Sedes y salas anidadas
SEDES = [
    {
        "nombre": "Sede Palermo",
        "direccion": "Av. Santa Fe 3200, CABA",
        "salas": [
            {"nombre": "Sala Zen", "capacidad": 18},
            {"nombre": "Sala Power", "capacidad": 28},
        ],
    },
    {
        "nombre": "Sede Belgrano",
        "direccion": "Vuelta de Obligado 2100, CABA",
        "salas": [
            {"nombre": "Sala Spin", "capacidad": 22},
            {"nombre": "Sala Box", "capacidad": 16},
            {"nombre": "Sala Flow", "capacidad": 14},
        ],
    },
]

DISCIPLINAS = [
    {"nombre": "Yoga", "descripcion": "Clases de yoga para todos los niveles."},
    {"nombre": "Pilates", "descripcion": "Fortalecimiento y flexibilidad en colchoneta y reformer."},
    {"nombre": "Funcional", "descripcion": "Entrenamiento funcional en circuito."},
    {"nombre": "Spinning", "descripcion": "Ciclismo indoor con música."},
    {"nombre": "HIIT", "descripcion": "Alta intensidad por intervalos."},
    {"nombre": "Boxeo", "descripcion": "Técnica y acondicionamiento."},
    {"nombre": "Stretching", "descripcion": "Movilidad y recuperación muscular."},
]

PROFESORES = [
    {"nombre": "Carlos", "apellido": "Sánchez"},
    {"nombre": "Ana", "apellido": "Martínez"},
    {"nombre": "Roberto", "apellido": "García"},
    {"nombre": "Lucía", "apellido": "Fernández"},
    {"nombre": "Martín", "apellido": "Díaz"},
    {"nombre": "Valentina", "apellido": "Ruiz"},
    {"nombre": "Diego", "apellido": "Morales"},
    {"nombre": "Camila", "apellido": "Torres"},
    {"nombre": "Facundo", "apellido": "López"},
    {"nombre": "Sofía", "apellido": "Acosta"},
]

# Clases: (disciplina, sede, sala, profesor, dia_semana, hora, duracion_min, cupo)
CLASES = [
    # Lunes
    ("Yoga",       "Sede Palermo",  "Sala Zen",   "Carlos",    "Sánchez",   0, time(7,  0), 60, 16),
    ("Pilates",    "Sede Belgrano", "Sala Flow",  "Ana",       "Martínez",  0, time(8,  0), 60, 12),
    ("Funcional",  "Sede Palermo",  "Sala Power", "Roberto",   "García",    0, time(10, 0), 60, 24),
    ("Spinning",   "Sede Belgrano", "Sala Spin",  "Lucía",     "Fernández", 0, time(18, 0), 60, 20),
    ("HIIT",       "Sede Palermo",  "Sala Power", "Martín",    "Díaz",      0, time(19, 0), 60, 22),
    ("Boxeo",      "Sede Belgrano", "Sala Box",   "Valentina", "Ruiz",      0, time(20, 0), 60, 14),
    # Martes
    ("Yoga",       "Sede Palermo",  "Sala Zen",   "Camila",    "Torres",    1, time(7,  0), 60, 16),
    ("Pilates",    "Sede Belgrano", "Sala Flow",  "Ana",       "Martínez",  1, time(9,  0), 60, 12),
    ("Funcional",  "Sede Palermo",  "Sala Power", "Facundo",   "López",     1, time(10, 0), 60, 24),
    ("Spinning",   "Sede Belgrano", "Sala Spin",  "Sofía",     "Acosta",    1, time(17, 0), 60, 20),
    ("Funcional",  "Sede Palermo",  "Sala Power", "Roberto",   "García",    1, time(19, 0), 60, 24),
    ("Stretching", "Sede Belgrano", "Sala Flow",  "Diego",     "Morales",   1, time(20, 0), 60, 12),
    # Miércoles
    ("Spinning",   "Sede Belgrano", "Sala Spin",  "Lucía",     "Fernández", 2, time(7,  0), 60, 20),
    ("Yoga",       "Sede Palermo",  "Sala Zen",   "Carlos",    "Sánchez",   2, time(8,  0), 60, 16),
    ("Pilates",    "Sede Belgrano", "Sala Flow",  "Camila",    "Torres",    2, time(18, 0), 60, 12),
    ("Funcional",  "Sede Palermo",  "Sala Power", "Facundo",   "López",     2, time(19, 0), 60, 24),
    # Jueves
    ("Pilates",    "Sede Palermo",  "Sala Zen",   "Ana",       "Martínez",  3, time(7,  0), 60, 14),
    ("Funcional",  "Sede Palermo",  "Sala Power", "Roberto",   "García",    3, time(9,  0), 60, 24),
    ("Spinning",   "Sede Belgrano", "Sala Spin",  "Sofía",     "Acosta",    3, time(10, 0), 60, 20),
    ("Yoga",       "Sede Palermo",  "Sala Zen",   "Camila",    "Torres",    3, time(18, 0), 60, 16),
    ("HIIT",       "Sede Palermo",  "Sala Power", "Martín",    "Díaz",      3, time(19, 0), 60, 22),
    # Viernes
    ("Yoga",       "Sede Palermo",  "Sala Zen",   "Carlos",    "Sánchez",   4, time(7,  0), 60, 16),
    ("Funcional",  "Sede Palermo",  "Sala Power", "Facundo",   "López",     4, time(8,  0), 60, 24),
    ("Spinning",   "Sede Belgrano", "Sala Spin",  "Lucía",     "Fernández", 4, time(17, 0), 60, 20),
    ("Pilates",    "Sede Belgrano", "Sala Flow",  "Ana",       "Martínez",  4, time(18, 0), 60, 12),
    ("Stretching", "Sede Belgrano", "Sala Flow",  "Diego",     "Morales",   4, time(20, 0), 60, 12),
    # Sábado
    ("Funcional",  "Sede Palermo",  "Sala Power", "Roberto",   "García",    5, time(8,  0), 60, 24),
    ("HIIT",       "Sede Palermo",  "Sala Power", "Martín",    "Díaz",      5, time(9,  0), 60, 22),
    ("Pilates",    "Sede Belgrano", "Sala Flow",  "Camila",    "Torres",    5, time(10, 0), 60, 12),
    ("Spinning",   "Sede Belgrano", "Sala Spin",  "Sofía",     "Acosta",    5, time(18, 0), 60, 20),
    # Domingo
    ("Yoga",       "Sede Palermo",  "Sala Zen",   "Carlos",    "Sánchez",   6, time(9,  0), 60, 18),
    ("Funcional",  "Sede Palermo",  "Sala Power", "Facundo",   "López",     6, time(10, 0), 60, 26),
    ("Spinning",   "Sede Belgrano", "Sala Spin",  "Lucía",     "Fernández", 6, time(11, 0), 60, 22),
    ("Stretching", "Sede Belgrano", "Sala Flow",  "Diego",     "Morales",   6, time(12, 0), 60, 12),
]

# Precios mensuales por disciplina (clase suelta = 50% del mensual)
PRECIOS_DISCIPLINA = {
    "Yoga":       Decimal("5200.00"),
    "Pilates":    Decimal("5800.00"),
    "Funcional":  Decimal("4800.00"),
    "Spinning":   Decimal("5000.00"),
    "HIIT":       Decimal("5500.00"),
    "Boxeo":      Decimal("6000.00"),
    "Stretching": Decimal("4200.00"),
}


# ---------------------------------------------------------------------------
# Helpers para construir períodos relativos a hoy
# ---------------------------------------------------------------------------

def _primer_dia(año, mes):
    return date(año, mes, 1)


def _ultimo_dia(año, mes):
    siguiente = date(año, mes % 12 + 1, 1) if mes < 12 else date(año + 1, 1, 1)
    return siguiente - timedelta(days=1)


def _periodos_relativos_a_hoy():
    """
    Devuelve dos períodos de cobro relativos a la fecha actual:
      - 'pasado': el mes calendario anterior al de hoy
      - 'actual': el mes calendario de hoy

    De esta forma el seed nunca queda desactualizado.
    """
    today = timezone.now().date()
    año_actual, mes_actual = today.year, today.month

    if mes_actual == 1:
        año_pasado, mes_pasado = año_actual - 1, 12
    else:
        año_pasado, mes_pasado = año_actual, mes_actual - 1

    if mes_actual == 12:
        año_futuro, mes_futuro = año_actual + 1, 1
    else:
        año_futuro, mes_futuro = año_actual, mes_actual + 1

    meses = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
        5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
    }

    return [
        {
            "nombre": f"{meses[mes_pasado]} {año_pasado}",
            "estado": "cerrado",
            "fecha_inicio_periodo": _primer_dia(año_pasado, mes_pasado),
            "fecha_fin_periodo": _ultimo_dia(año_pasado, mes_pasado),
            "apertura_abonados": _primer_dia(año_pasado, mes_pasado) - timedelta(days=15),
            "apertura_general": _primer_dia(año_pasado, mes_pasado),
        },
        {
            "nombre": f"{meses[mes_actual]} {año_actual}",
            "estado": "activo",
            "fecha_inicio_periodo": _primer_dia(año_actual, mes_actual),
            "fecha_fin_periodo": _ultimo_dia(año_actual, mes_actual),
            "apertura_abonados": _primer_dia(año_actual, mes_actual) - timedelta(days=15),
            "apertura_general": _primer_dia(año_actual, mes_actual),
        },
        {
            "nombre": f"{meses[mes_futuro]} {año_futuro}",
            "estado": "proximo",
            "fecha_inicio_periodo": _primer_dia(año_futuro, mes_futuro),
            "fecha_fin_periodo": _ultimo_dia(año_futuro, mes_futuro),
            "apertura_abonados": _primer_dia(año_futuro, mes_futuro) - timedelta(days=15),
            "apertura_general": _primer_dia(año_futuro, mes_futuro),
        },
    ]


# ---------------------------------------------------------------------------
# Comando
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Pobla la base de datos con datos de desarrollo/demo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Elimina todos los datos existentes antes de sembrar.",
        )

    def handle(self, *args, **options):
        from django.apps import apps

        User = apps.get_model("users", "User")
        Sede = apps.get_model("classes", "Sede")
        Sala = apps.get_model("classes", "Sala")
        Disciplina = apps.get_model("classes", "Disciplina")
        Teacher = apps.get_model("classes", "Teacher")
        Class = apps.get_model("classes", "Class")
        Inscripcion = apps.get_model("classes", "Inscripcion")
        PeriodoCobro = apps.get_model("payments", "PeriodoCobro")
        PrecioClase = apps.get_model("payments", "PrecioClase")
        Pago = apps.get_model("payments", "Pago")
        PagoInscripcion = apps.get_model("payments", "PagoInscripcion")
        Credito = apps.get_model("payments", "Credito")

        if options["reset"]:
            self._reset(User, Sede, Sala, Disciplina, Teacher, Class, Inscripcion, PeriodoCobro, PrecioClase, Pago, PagoInscripcion, Credito)

        self._seed_usuarios(User)
        sedes_obj, salas_obj = self._seed_sedes_salas(Sede, Sala)
        disciplinas_obj = self._seed_disciplinas(Disciplina)
        profesores_obj = self._seed_profesores(Teacher)
        clases_obj = self._seed_clases(
            Class, sedes_obj, salas_obj, disciplinas_obj, profesores_obj
        )
        periodos_obj = self._seed_periodos(PeriodoCobro)
        self._seed_precios(PrecioClase, clases_obj, disciplinas_obj, periodos_obj)
        self._seed_inscripciones_y_pagos(
            User, Class, Inscripcion, PeriodoCobro,
            Pago, PagoInscripcion, Credito,
            Disciplina, Sede, Sala,
            clases_obj, periodos_obj,
        )

        self.stdout.write(self.style.SUCCESS("✓ Seed completado."))

    # -----------------------------------------------------------------------
    # Reset
    # -----------------------------------------------------------------------

    def _reset(self, User, Sede, Sala, Disciplina, Teacher, Class, Inscripcion, PeriodoCobro, PrecioClase, Pago, PagoInscripcion, Credito):
        self.stdout.write("  Eliminando datos existentes...")
        # El orden respeta las FK (primero los dependientes)
        PagoInscripcion.objects.all().delete()
        Pago.objects.all().delete()
        Credito.objects.all().delete()
        Inscripcion.objects.all().delete()
        PrecioClase.objects.all().delete()
        PeriodoCobro.objects.all().delete()
        Class.objects.all().delete()
        Teacher.objects.all().delete()
        Disciplina.objects.all().delete()
        Sala.objects.all().delete()
        Sede.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        User.objects.all().delete()
        self.stdout.write("  Datos eliminados.")

    # -----------------------------------------------------------------------
    # Usuarios
    # -----------------------------------------------------------------------

    def _seed_usuarios(self, User):
        created = skipped = 0
        for data in USUARIOS:
            if User.objects.filter(email=data["email"]).exists():
                skipped += 1
                continue

            raw_password = data.pop("raw_password")
            # telefono_emergencia es opcional; si no está, derivarlo del DNI
            if data.get("rol") == "CLIENTE" and not data.get("telefono_emergencia"):
                data["telefono_emergencia"] = f"35155{str(data['dni'])[-6:]}"

            User.objects.create(
                username=data["email"],
                password=make_password(raw_password),
                **data,
            )
            created += 1

        self.stdout.write(f"  Usuarios: {created} creados, {skipped} existentes.")

    # -----------------------------------------------------------------------
    # Infraestructura: sedes y salas
    # -----------------------------------------------------------------------

    def _seed_sedes_salas(self, Sede, Sala):
        sedes_obj = {}
        salas_obj = {}  # (sede_nombre, sala_nombre) -> Sala

        for sede_data in SEDES:
            salas_data = sede_data.pop("salas")
            sede, _ = Sede.objects.get_or_create(
                nombre=sede_data["nombre"],
                defaults={"direccion": sede_data["direccion"]},
            )
            sedes_obj[sede.nombre] = sede

            for sala_data in salas_data:
                sala, _ = Sala.objects.get_or_create(
                    nombre=sala_data["nombre"],
                    sede=sede,
                    defaults={"capacidad": sala_data["capacidad"]},
                )
                salas_obj[(sede.nombre, sala.nombre)] = sala

        self.stdout.write(
            f"  Sedes: {len(sedes_obj)}, Salas: {len(salas_obj)}."
        )
        return sedes_obj, salas_obj

    # -----------------------------------------------------------------------
    # Disciplinas
    # -----------------------------------------------------------------------

    def _seed_disciplinas(self, Disciplina):
        disciplinas_obj = {}
        for data in DISCIPLINAS:
            obj, _ = Disciplina.objects.get_or_create(
                nombre=data["nombre"],
                defaults={"descripcion": data["descripcion"]},
            )
            disciplinas_obj[obj.nombre] = obj
        self.stdout.write(f"  Disciplinas: {len(disciplinas_obj)}.")
        return disciplinas_obj

    # -----------------------------------------------------------------------
    # Profesores
    # -----------------------------------------------------------------------

    def _seed_profesores(self, Teacher):
        profesores_obj = {}
        for data in PROFESORES:
            obj, _ = Teacher.objects.get_or_create(
                nombre=data["nombre"],
                apellido=data["apellido"],
            )
            profesores_obj[(obj.nombre, obj.apellido)] = obj
        self.stdout.write(f"  Profesores: {len(profesores_obj)}.")
        return profesores_obj

    # -----------------------------------------------------------------------
    # Clases
    # -----------------------------------------------------------------------

    def _seed_clases(self, Class, sedes_obj, salas_obj, disciplinas_obj, profesores_obj):
        clases_obj = {}
        created = skipped = 0

        for row in CLASES:
            disciplina_nombre, sede_nombre, sala_nombre, prof_nombre, prof_apellido, \
                dia, hora, duracion_min, cupo = row

            disciplina = disciplinas_obj[disciplina_nombre]
            sala = salas_obj[(sede_nombre, sala_nombre)]
            profesor = profesores_obj[(prof_nombre, prof_apellido)]

            obj, was_created = Class.objects.get_or_create(
                disciplina=disciplina,
                sala=sala,
                dia_semana=dia,
                hora_inicio=hora,
                defaults={
                    "profesor": profesor,
                    "duracion": timedelta(minutes=duracion_min),
                    "cupo_maximo": cupo,
                    "estado": "disponible",
                },
            )
            key = (disciplina_nombre, sede_nombre, sala_nombre, dia, hora)
            clases_obj[key] = obj
            if was_created:
                created += 1
            else:
                skipped += 1

        self.stdout.write(f"  Clases: {created} creadas, {skipped} existentes.")
        return clases_obj

    # -----------------------------------------------------------------------
    # Períodos de cobro (relativos a hoy)
    # -----------------------------------------------------------------------

    def _seed_periodos(self, PeriodoCobro):
        periodos_obj = {}
        for data in _periodos_relativos_a_hoy():
            estado = data.pop("estado")
            obj, _ = PeriodoCobro.objects.update_or_create(
                nombre=data["nombre"],
                defaults={
                    "fecha_inicio_periodo": data["fecha_inicio_periodo"],
                    "fecha_fin_periodo": data["fecha_fin_periodo"],
                    "apertura_abonados": data["apertura_abonados"],
                    "apertura_general": data["apertura_general"],
                },
            )
            periodos_obj[estado] = obj
            self.stdout.write(
                f"  Período «{obj.nombre}» [{estado}]: "
                f"{obj.fecha_inicio_periodo} → {obj.fecha_fin_periodo}"
            )
        return periodos_obj  # {"cerrado": <obj>, "activo": <obj>}

    # -----------------------------------------------------------------------
    # Precios
    # -----------------------------------------------------------------------

    def _seed_precios(self, PrecioClase, clases_obj, disciplinas_obj, periodos_obj):
        created = 0
        for clase in clases_obj.values():
            disciplina_nombre = clase.disciplina.nombre
            monto = PRECIOS_DISCIPLINA.get(disciplina_nombre)
            if not monto:
                continue
            for periodo in periodos_obj.values():
                _, was_created = PrecioClase.objects.get_or_create(
                    clase=clase,
                    periodo=periodo,
                    defaults={"monto": monto},
                )
                if was_created:
                    created += 1
        self.stdout.write(f"  Precios: {created} creados.")

    # -----------------------------------------------------------------------
    # Inscripciones, pagos y créditos de ejemplo
    # -----------------------------------------------------------------------

    def _seed_inscripciones_y_pagos(
        self,
        User, Class, Inscripcion, PeriodoCobro,
        Pago, PagoInscripcion, Credito,
        Disciplina, Sede, Sala,
        clases_obj, periodos_obj,
    ):
        periodo_pasado = periodos_obj.get("cerrado")
        periodo_actual = periodos_obj.get("activo")
        periodo_futuro = periodos_obj.get("proximo")

        # Helpers locales
        def get_user(email):
            return User.objects.get(email=email)

        def get_clase(disciplina_nombre, sede_nombre, sala_nombre, dia, hora):
            return clases_obj.get(
                (disciplina_nombre, sede_nombre, sala_nombre, dia, hora)
            )

        def crear_inscripcion(usuario, clase, periodo, tipo, estado):
            """Crea una inscripción si no existe ya una no-cancelada."""
            if Inscripcion.objects.filter(
                usuario=usuario, clase=clase, periodo=periodo
            ).exclude(estado=Inscripcion.Estado.CANCELADA).exists():
                return None

            insc = Inscripcion.objects.create(
                usuario=usuario,
                clase=clase,
                periodo=periodo,
                tipo=tipo,
                estado=estado,
            )
            # Override auto_now_add
            fecha_ins = timezone.now().replace(
                year=periodo.fecha_inicio_periodo.year,
                month=periodo.fecha_inicio_periodo.month,
                day=1, hour=9, minute=0, second=0
            )
            Inscripcion.objects.filter(pk=insc.pk).update(fecha_inscripcion=fecha_ins)
            # Genera ocurrencias automáticamente (ignorando limitación temporal del sistema)
            from apps.classes.models import InscripcionOcurrencia
            if tipo == Inscripcion.Tipo.MENSUAL:
                from apps.classes.services import ocurrencias_detalle_en_periodo
                fechas = ocurrencias_detalle_en_periodo(clase, periodo, desde_fecha=periodo.fecha_inicio_periodo)
                InscripcionOcurrencia.objects.bulk_create([
                    InscripcionOcurrencia(
                        inscripcion=insc,
                        fecha_clase=fecha,
                        estado=InscripcionOcurrencia.Estado.ACTIVA,
                    ) for fecha in fechas
                ])
            elif tipo == Inscripcion.Tipo.CLASE_SUELTA:
                from apps.classes.services import ocurrencias_detalle_en_periodo
                fechas = ocurrencias_detalle_en_periodo(clase, periodo, desde_fecha=periodo.fecha_inicio_periodo)
                if fechas:
                    InscripcionOcurrencia.objects.create(
                        inscripcion=insc,
                        fecha_clase=fechas[0],
                        estado=InscripcionOcurrencia.Estado.ACTIVA,
                    )
            return insc

        def crear_pago(usuario, periodo, monto, metodo, estado, inscripciones_montos=None):
            """
            inscripciones_montos es una lista de tuplas: (inscripcion, monto_aplicado)
            """
            if Pago.objects.filter(
                usuario=usuario, periodo=periodo, monto=monto,
                metodo=metodo, estado=estado,
            ).exists():
                return None
            pago = Pago.objects.create(
                usuario=usuario, periodo=periodo,
                monto=monto, metodo=metodo, estado=estado,
            )
            # Override auto_now_add
            fecha_pg = timezone.now().replace(
                year=periodo.fecha_inicio_periodo.year,
                month=periodo.fecha_inicio_periodo.month,
                day=5, hour=10, minute=0, second=0
            )
            Pago.objects.filter(pk=pago.pk).update(fecha_pago=fecha_pg)
            if inscripciones_montos:
                for insc, monto_aplicado in inscripciones_montos:
                    PagoInscripcion.objects.get_or_create(
                        pago=pago, inscripcion=insc,
                        defaults={"monto_aplicado": monto_aplicado},
                    )
            return pago

        inscripciones_creadas = 0
        pagos_creados = 0
        creditos_creados = 0

        # ── Período pasado ──
        if periodo_pasado:
            juan = get_user("juan.perez@mail.com")
            clase_funcional_lun = get_clase("Funcional", "Sede Palermo", "Sala Power", 0, time(10, 0))
            if clase_funcional_lun:
                insc = crear_inscripcion(
                    juan, clase_funcional_lun, periodo_pasado,
                    Inscripcion.Tipo.CLASE_SUELTA, Inscripcion.Estado.RESERVADA,
                )
                if insc:
                    inscripciones_creadas += 1
                    pago = crear_pago(
                        juan, periodo_pasado,
                        PRECIOS_DISCIPLINA["Funcional"] / 2,
                        Pago.Metodo.MERCADOPAGO, Pago.Estado.COMPLETADO,
                        [(insc, PRECIOS_DISCIPLINA["Funcional"] / 2)],
                    )
                    if pago:
                        pagos_creados += 1

            diego = get_user("diego.torres@mail.com")
            clase_spinning_dom = get_clase("Spinning", "Sede Belgrano", "Sala Spin", 6, time(11, 0))
            if clase_spinning_dom:
                insc_diego = crear_inscripcion(
                    diego, clase_spinning_dom, periodo_pasado,
                    Inscripcion.Tipo.MENSUAL, Inscripcion.Estado.RESERVADA,
                )
                if insc_diego:
                    inscripciones_creadas += 1
                    pago = crear_pago(
                        diego, periodo_pasado,
                        PRECIOS_DISCIPLINA["Spinning"],
                        Pago.Metodo.MERCADOPAGO, Pago.Estado.COMPLETADO,
                        [(insc_diego, PRECIOS_DISCIPLINA["Spinning"])],
                    )
                    if pago:
                        pagos_creados += 1

        # ── Período actual ──
        if periodo_actual:
            martin = get_user("martin.lopez@mail.com")
            clase_yoga_lun = get_clase("Yoga", "Sede Palermo", "Sala Zen", 0, time(7, 0))
            if clase_yoga_lun:
                insc = crear_inscripcion(
                    martin, clase_yoga_lun, periodo_actual,
                    Inscripcion.Tipo.CLASE_SUELTA, Inscripcion.Estado.PENDIENTE_PAGO,
                )
                if insc:
                    inscripciones_creadas += 1

            sofia = get_user("sofia.ramirez@mail.com")
            clase_pilates_lun = get_clase("Pilates", "Sede Belgrano", "Sala Flow", 0, time(8, 0))
            if clase_pilates_lun:
                insc = crear_inscripcion(
                    sofia, clase_pilates_lun, periodo_actual,
                    Inscripcion.Tipo.CLASE_SUELTA, Inscripcion.Estado.PENDIENTE_PAGO,
                )
                if insc:
                    inscripciones_creadas += 1
                    monto_parcial = PRECIOS_DISCIPLINA["Pilates"] / 2
                    pago = crear_pago(
                        sofia, periodo_actual, monto_parcial,
                        Pago.Metodo.MERCADOPAGO, Pago.Estado.COMPLETADO,
                        [(insc, monto_parcial)],
                    )
                    if pago:
                        pagos_creados += 1

            # Guadalupe: Múltiples inscripciones en el mismo período, pagadas juntas
            guadalupe = get_user("guadalupe@email.com")
            clase_funcional_mar = get_clase("Funcional", "Sede Palermo", "Sala Power", 1, time(10, 0))
            clase_stretching_mar = get_clase("Stretching", "Sede Belgrano", "Sala Flow", 1, time(20, 0))
            
            if clase_funcional_mar and clase_stretching_mar:
                insc1 = crear_inscripcion(
                    guadalupe, clase_funcional_mar, periodo_actual,
                    Inscripcion.Tipo.MENSUAL, Inscripcion.Estado.RESERVADA,
                )
                insc2 = crear_inscripcion(
                    guadalupe, clase_stretching_mar, periodo_actual,
                    Inscripcion.Tipo.MENSUAL, Inscripcion.Estado.RESERVADA,
                )
                if insc1 and insc2:
                    inscripciones_creadas += 2
                    monto_total = PRECIOS_DISCIPLINA["Funcional"] + PRECIOS_DISCIPLINA["Stretching"]
                    pago = crear_pago(
                        guadalupe, periodo_actual, monto_total,
                        Pago.Metodo.MERCADOPAGO, Pago.Estado.COMPLETADO,
                        [(insc1, PRECIOS_DISCIPLINA["Funcional"]), (insc2, PRECIOS_DISCIPLINA["Stretching"])],
                    )
                    if pago:
                        pagos_creados += 1

            # Enrique: Inscrito mensualmente y pagó con saldo a favor / crédito
            enrique = get_user("enrique@email.com")
            clase_boxeo_lun = get_clase("Boxeo", "Sede Belgrano", "Sala Box", 0, time(20, 0))
            if clase_boxeo_lun:
                insc_enrique = crear_inscripcion(
                    enrique, clase_boxeo_lun, periodo_actual,
                    Inscripcion.Tipo.MENSUAL, Inscripcion.Estado.RESERVADA,
                )
                if insc_enrique:
                    inscripciones_creadas += 1
                    pago = crear_pago(
                        enrique, periodo_actual, PRECIOS_DISCIPLINA["Boxeo"],
                        Pago.Metodo.CREDITO, Pago.Estado.COMPLETADO,
                        [(insc_enrique, PRECIOS_DISCIPLINA["Boxeo"])],
                    )
                    if pago:
                        pagos_creados += 1

            # HIIT lunes 19:00 — llenamos hasta el cupo y más allá (lista de espera)
            clase_hiit_lun = get_clase("HIIT", "Sede Palermo", "Sala Power", 0, time(19, 0))
            if clase_hiit_lun:
                cupo = clase_hiit_lun.cupo_maximo # es 22
                clientes_hiit = [
                    "juan.perez@mail.com", "diego.torres@mail.com",
                    "sofia.ramirez@mail.com", "enrique@email.com",
                    "guadalupe@email.com", "martin.lopez@mail.com",
                    "valentina.morales@mail.com", "lucas.fernandez@mail.com",
                    "camila.sosa@mail.com", "tomas.acosta@mail.com",
                    "florencia.ruiz@mail.com", "mariana.gomez@mail.com",
                    "nicolas.herrera@mail.com", "agustina.molina@mail.com",
                    "facundo.castro@mail.com", "paula.vega@mail.com",
                    "santiago.ibarra@mail.com", "romina.silva@mail.com",
                    "german.ortiz@mail.com", "carla.medina@mail.com",
                    "leandro.romero@mail.com", "belen.navarro@mail.com",
                    # Extras para lista de espera:
                    "franco.mendez@mail.com", "juliana.campos@mail.com",
                    "maximiliano.suarez@mail.com", "melina.rios@mail.com"
                ]
                for i, email in enumerate(clientes_hiit):
                    estado = (
                        Inscripcion.Estado.RESERVADA
                        if i < cupo
                        else Inscripcion.Estado.ESPERA
                    )
                    tipo = Inscripcion.Tipo.MENSUAL if i % 3 == 0 else Inscripcion.Tipo.CLASE_SUELTA
                    insc = crear_inscripcion(
                        get_user(email), clase_hiit_lun, periodo_actual,
                        tipo, estado,
                    )
                    if insc:
                        inscripciones_creadas += 1
                        # Los que reservaron y son mensuales o sueltos, pagaron
                        if estado == Inscripcion.Estado.RESERVADA:
                            monto = PRECIOS_DISCIPLINA["HIIT"] if tipo == Inscripcion.Tipo.MENSUAL else PRECIOS_DISCIPLINA["HIIT"] / 2
                            pago = crear_pago(
                                get_user(email), periodo_actual, monto,
                                Pago.Metodo.MERCADOPAGO, Pago.Estado.COMPLETADO,
                                [(insc, monto)],
                            )
                            if pago:
                                pagos_creados += 1

            # Crédito disponible para Enrique en otra disciplina
            yoga_disciplina = Disciplina.objects.get(nombre="Yoga")
            _, was_created = Credito.objects.get_or_create(
                usuario=enrique,
                periodo=periodo_actual,
                disciplina=yoga_disciplina,
                defaults={"estado": Credito.Estado.DISPONIBLE},
            )
            if was_created:
                creditos_creados += 1

        # ── Período futuro: Reservas mensuales con prioridad y lista de espera de sueltos ──
        if periodo_futuro:
            # Los abonados pueden reservar antes
            juan = get_user("juan.perez@mail.com")
            clase_funcional_jue = get_clase("Funcional", "Sede Palermo", "Sala Power", 3, time(9, 0))
            if clase_funcional_jue:
                # Abonado mensual -> RESERVADA
                insc = crear_inscripcion(
                    juan, clase_funcional_jue, periodo_futuro,
                    Inscripcion.Tipo.MENSUAL, Inscripcion.Estado.RESERVADA,
                )
                if insc:
                    inscripciones_creadas += 1

            martin = get_user("martin.lopez@mail.com")
            if clase_funcional_jue:
                # Clase suelta antes de la apertura general -> ESPERA
                insc = crear_inscripcion(
                    martin, clase_funcional_jue, periodo_futuro,
                    Inscripcion.Tipo.CLASE_SUELTA, Inscripcion.Estado.ESPERA,
                )
                if insc:
                    inscripciones_creadas += 1

        self.stdout.write(
            f"  Inscripciones: {inscripciones_creadas} creadas, "
            f"Pagos: {pagos_creados} creados, "
            f"Créditos: {creditos_creados} creados."
        )
