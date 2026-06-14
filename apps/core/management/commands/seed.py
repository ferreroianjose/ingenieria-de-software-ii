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

import random
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
    Devuelve varios períodos de cobro relativos a la fecha actual:
      - 'cerrado_X': meses pasados
      - 'activo': el mes calendario de hoy
      - 'proximo': el próximo mes
    """
    today = timezone.now().date()
    meses_nombre = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
        5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
    }

    periodos = []

    for delta in range(-4, 2):
        mes = today.month + delta
        año = today.year
        while mes < 1:
            mes += 12
            año -= 1
        while mes > 12:
            mes -= 12
            año += 1

        if delta < 0:
            estado = f"cerrado_{abs(delta)}"
        elif delta > 0:
            estado = "proximo"
        else:
            estado = "activo"

        if delta == -1:
            estado = "cerrado"

        periodos.append({
            "nombre": f"{meses_nombre[mes]} {año}",
            "estado": estado,
            "fecha_inicio_periodo": _primer_dia(año, mes),
            "fecha_fin_periodo": _ultimo_dia(año, mes),
            "apertura_abonados": _primer_dia(año, mes) - timedelta(days=15),
            "apertura_general": _primer_dia(año, mes),
        })

    return periodos


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

        self._seed_demo_case(User, Class, Inscripcion, PeriodoCobro, Pago, PagoInscripcion, PrecioClase)

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
            if data.get("rol") == "CLIENTE" and not data.get("telefono_emergencia"):
                data["telefono_emergencia"] = f"35155{str(data['dni'])[-6:]}"

            User.objects.create(
                username=data["email"],
                password=make_password(raw_password),
                **data,
            )
            created += 1

        # Generar 150 usuarios aleatorios extra para mayor realismo en las planillas
        nombres = ["Juan", "Pedro", "Maria", "Ana", "Luis", "Carlos", "Sofia", "Lucia", "Martina", "Matias", "Facundo", "Tomas", "Camila", "Valentina", "Florencia", "Agustin", "Ignacio", "Nicolas"]
        apellidos = ["Gomez", "Perez", "Rodriguez", "Fernandez", "Lopez", "Martinez", "Gonzalez", "Garcia", "Silva", "Romero", "Sosa", "Torres", "Ruiz", "Diaz"]

        for i in range(150):
            dni = f"{random.randint(30000000, 45000000)}"
            email = f"cliente_rnd_{i}_{dni}@mail.com"
            if User.objects.filter(email=email).exists():
                continue

            fn = random.choice(nombres)
            ln = random.choice(apellidos)

            User.objects.create(
                username=email,
                email=email,
                password=make_password("cliente123"),
                first_name=fn,
                last_name=ln,
                rol="CLIENTE",
                dni=dni,
                fecha_nacimiento=date(random.randint(1980, 2005), random.randint(1, 12), random.randint(1, 28)),
                estado_constancia=random.choices(["APROBADA", "PENDIENTE", "RECHAZADA"], weights=[0.8, 0.15, 0.05])[0],
                telefono_emergencia=f"35155{dni[-6:]}"
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
        asistencias_creadas = 0

        import random
        random.seed(42)  # Determinismo para el seed

        todos_usuarios = list(User.objects.filter(rol="CLIENTE"))
        todas_clases = list(Class.objects.select_related('disciplina'))

        for estado, periodo in periodos_obj.items():
            if estado == "proximo":
                # Menos usuarios pre-inscriptos para el mes futuro
                usuarios_activos = random.sample(todos_usuarios, k=min(8, len(todos_usuarios)))
                for usuario in usuarios_activos:
                    clase = random.choice(todas_clases)
                    insc = crear_inscripcion(usuario, clase, periodo, Inscripcion.Tipo.MENSUAL, Inscripcion.Estado.RESERVADA)
                    if insc:
                        inscripciones_creadas += 1
            else:
                # Períodos pasados y actuales
                usuarios_activos = random.sample(todos_usuarios, k=min(32, len(todos_usuarios)))
                for usuario in usuarios_activos:
                    num_clases = random.choice([2, 3, 4])
                    clases_elegidas = random.sample(todas_clases, k=num_clases)
                    for clase in clases_elegidas:
                        tipo = random.choices([Inscripcion.Tipo.MENSUAL, Inscripcion.Tipo.CLASE_SUELTA], weights=[0.8, 0.2])[0]
                        insc = crear_inscripcion(usuario, clase, periodo, tipo, Inscripcion.Estado.RESERVADA)
                        if insc:
                            inscripciones_creadas += 1
                            monto = PRECIOS_DISCIPLINA.get(clase.disciplina.nombre, 3000)
                            if tipo == Inscripcion.Tipo.CLASE_SUELTA:
                                monto = monto / 2

                            # Simular cancelaciones en algunas ocurrencias (solo en pasado/actual)
                            from apps.classes.models import InscripcionOcurrencia
                            for oc in insc.ocurrencias.all():
                                if random.random() < 0.15:  # 15% chance of cancellation
                                    oc.estado = InscripcionOcurrencia.Estado.CANCELADA
                                    # 50% de las veces otorga crédito si canceló a tiempo
                                    if random.random() < 0.5:
                                        c = Credito.objects.create(
                                            usuario=usuario,
                                            periodo=periodo,
                                            disciplina=clase.disciplina,
                                            estado=Credito.Estado.DISPONIBLE
                                        )
                                        oc.otorga_credito = True
                                        oc.credito = c
                                        creditos_creados += 1
                                    oc.save()

                            # Check if user has an available credit for this discipline
                            credito_disponible = Credito.objects.filter(
                                usuario=usuario,
                                disciplina=clase.disciplina,
                                estado=Credito.Estado.DISPONIBLE
                            ).first()

                            metodo_pago = Pago.Metodo.MERCADOPAGO
                            if credito_disponible:
                                credito_disponible.estado = Credito.Estado.UTILIZADO
                                credito_disponible.save()
                                metodo_pago = Pago.Metodo.CREDITO

                            pago = crear_pago(
                                usuario, periodo, monto, metodo_pago, Pago.Estado.COMPLETADO, [(insc, monto)]
                            )
                            if pago:
                                pagos_creados += 1

                            # Simular asistencia para ocurrencias pasadas o actuales
                            from apps.attendance.models import Asistencia
                            import datetime

                            now = timezone.now()
                            for oc in insc.ocurrencias.all():
                                if oc.estado == InscripcionOcurrencia.Estado.ACTIVA and oc.fecha_clase <= now:
                                    # 95% de probabilidad de asistir
                                    if random.random() < 0.95:
                                        a = Asistencia.objects.create(
                                            inscripcion=insc,
                                            metodo=random.choice([Asistencia.Metodo.QR, Asistencia.Metodo.MANUAL])
                                        )
                                        arrival_time = oc.fecha_clase - datetime.timedelta(minutes=random.randint(2, 15))
                                        Asistencia.objects.filter(pk=a.pk).update(fecha_hora_ingreso=arrival_time)
                                        asistencias_creadas += 1

        self.stdout.write(
            f"  Inscripciones: {inscripciones_creadas} creadas, "
            f"Pagos: {pagos_creados} creados, "
            f"Créditos: {creditos_creados} creados, "
            f"Asistencias: {asistencias_creadas} creadas."
        )

    # -----------------------------------------------------------------------
    # Caso de Demo Específico (Seña y Pago)
    # -----------------------------------------------------------------------

    def _seed_demo_case(self, User, Class, Inscripcion, PeriodoCobro, Pago, PagoInscripcion, PrecioClase):
        from apps.classes.services import obtener_periodo_activo_si_hay
        from apps.classes.ocurrencias import generar_ocurrencias_mensual

        today = timezone.localdate()
        dia_semana = today.weekday()

        clases_hoy = list(Class.objects.filter(dia_semana=dia_semana)[:2])
        if len(clases_hoy) < 2:
            return

        c1, c2 = clases_hoy

        user, _ = User.objects.get_or_create(
            email="demo@mail.com",
            defaults={
                "username": "demo@mail.com",
                "password": make_password("cliente123"),
                "first_name": "Demo",
                "last_name": "Asistencia",
                "dni": "99999999",
                "rol": "CLIENTE",
                "estado_constancia": "PENDIENTE",
                "fecha_nacimiento": date(2011, 1, 1)
            }
        )

        periodo = obtener_periodo_activo_si_hay()
        if not periodo:
            return

        Inscripcion.objects.filter(usuario=user, periodo=periodo).delete()

        i1 = Inscripcion.objects.create(
            usuario=user, clase=c1, periodo=periodo,
            tipo=Inscripcion.Tipo.MENSUAL, estado=Inscripcion.Estado.RESERVADA
        )

        i2 = Inscripcion.objects.create(
            usuario=user, clase=c2, periodo=periodo,
            tipo=Inscripcion.Tipo.MENSUAL, estado=Inscripcion.Estado.RESERVADA
        )

        p1_obj = PrecioClase.objects.filter(clase=c1, periodo=periodo).first()
        p2_obj = PrecioClase.objects.filter(clase=c2, periodo=periodo).first()

        monto_c1 = p1_obj.monto if p1_obj else Decimal("3000.00")
        monto_c2 = p2_obj.monto if p2_obj else Decimal("3000.00")

        # Pago Seña (mitad)
        pago1 = Pago.objects.create(
            usuario=user, periodo=periodo, monto=monto_c1 / 2,
            metodo=Pago.Metodo.EFECTIVO, estado=Pago.Estado.COMPLETADO
        )
        PagoInscripcion.objects.create(pago=pago1, inscripcion=i1, monto_aplicado=monto_c1 / 2)

        # Pago Total
        pago2 = Pago.objects.create(
            usuario=user, periodo=periodo, monto=monto_c2,
            metodo=Pago.Metodo.EFECTIVO, estado=Pago.Estado.COMPLETADO
        )
        PagoInscripcion.objects.create(pago=pago2, inscripcion=i2, monto_aplicado=monto_c2)

        generar_ocurrencias_mensual(i1)
        generar_ocurrencias_mensual(i2)

        self.stdout.write("  Caso de demo (Seña y Paga en el día) creado exitosamente.")
