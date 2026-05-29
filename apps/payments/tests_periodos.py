from datetime import date, datetime, time, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.classes.models import Class, Inscripcion
from apps.classes.services import ocurrencias_clase_en_ventana
from apps.payments.models import PeriodoCobro
from apps.payments.periodos import (
    en_ventana_preinscripcion_abonados,
    periodo_conteniendo_fecha,
    periodos_elegibles_clase_suelta,
    periodos_elegibles_mensual,
)


class PeriodosInscripcionTests(TestCase):
    def setUp(self):
        self.mayo = PeriodoCobro.objects.create(
            nombre="Mayo 2026",
            fecha_inicio_periodo=date(2026, 5, 1),
            fecha_fin_periodo=date(2026, 5, 31),
            apertura_abonados=date(2026, 4, 15),
            apertura_general=date(2026, 5, 1),
        )
        self.junio = PeriodoCobro.objects.create(
            nombre="Junio 2026",
            fecha_inicio_periodo=date(2026, 6, 1),
            fecha_fin_periodo=date(2026, 6, 30),
            apertura_abonados=date(2026, 5, 20),
            apertura_general=date(2026, 6, 1),
        )

    def test_preinscripcion_abonados_ultimos_diez_dias_mayo(self):
        hoy = date(2026, 5, 25)
        self.assertTrue(en_ventana_preinscripcion_abonados(self.junio, hoy))

    def test_mensual_incluye_vigente_y_siguiente_en_preinscripcion(self):
        hoy = date(2026, 5, 25)
        elegibles = periodos_elegibles_mensual(hoy)
        nombres = [p.nombre for p in elegibles]
        self.assertEqual(nombres, ["Mayo 2026", "Junio 2026"])

    def test_clase_suelta_periodos_en_ventana_de_tres_semanas(self):
        hoy = date(2026, 5, 25)
        elegibles = periodos_elegibles_clase_suelta(hoy)
        nombres = [p.nombre for p in elegibles]
        self.assertIn("Mayo 2026", nombres)
        self.assertIn("Junio 2026", nombres)

    def test_periodo_conteniendo_fecha(self):
        self.assertEqual(
            periodo_conteniendo_fecha(date(2026, 6, 3)).nombre, "Junio 2026"
        )


class OcurrenciasClaseSueltaTests(TestCase):
    def setUp(self):
        from apps.classes.models import Disciplina, Sala, Sede, Teacher

        self.periodo = PeriodoCobro.objects.create(
            nombre="Mayo 2026",
            fecha_inicio_periodo=date(2026, 5, 1),
            fecha_fin_periodo=date(2026, 5, 31),
            apertura_abonados=date(2026, 4, 15),
            apertura_general=date(2026, 5, 1),
        )
        disciplina = Disciplina.objects.create(nombre="Yoga Test")
        sede = Sede.objects.create(nombre="Sede Test")
        sala = Sala.objects.create(nombre="Sala 1", sede=sede)
        profesor = Teacher.objects.create(nombre="Profe", apellido="Uno")
        self.clase = Class.objects.create(
            disciplina=disciplina,
            sala=sala,
            profesor=profesor,
            dia_semana=1,
            hora_inicio=time(10, 0),
            duracion_minutos=60,
            cupo_maximo=10,
            estado="disponible",
        )

    def test_lista_ocurrencias_en_ventana(self):
        hoy = date(2026, 5, 25)
        ocurrencias = ocurrencias_clase_en_ventana(
            self.clase, dias=21, desde_fecha=hoy
        )
        self.assertGreaterEqual(len(ocurrencias), 2)
        fechas = [timezone.localdate(dt) for dt, _ in ocurrencias]
        self.assertTrue(all(f >= hoy for f in fechas))
        self.assertTrue(all(f <= hoy + timedelta(days=21) for f in fechas))
