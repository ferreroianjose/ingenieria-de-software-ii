from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone

from apps.classes.models import Class, Inscripcion
from apps.classes.services import ocurrencias_clase_en_ventana
from apps.payments.models import PeriodoCobro
from apps.payments.periodos import (
    en_ventana_preinscripcion_abonados,
    periodo_conteniendo_fecha,
    periodo_habilitado_clase_suelta,
    periodos_elegibles_clase_suelta,
    periodos_elegibles_mensual,
    requiere_precola_suelta,
    vencimiento_mensual_alcanzado,
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

    def test_clase_suelta_no_habilitada_antes_de_apertura_abonados(self):
        hoy = date(2026, 5, 10)
        self.assertFalse(periodo_habilitado_clase_suelta(self.junio, hoy))

    def test_clase_suelta_habilitada_como_precola_en_preinscripcion(self):
        hoy = date(2026, 5, 25)
        self.assertTrue(periodo_habilitado_clase_suelta(self.junio, hoy))
        self.assertTrue(requiere_precola_suelta(self.junio, hoy))

    def test_clase_suelta_no_requiere_precola_desde_apertura_general(self):
        hoy = date(2026, 6, 1)
        self.assertTrue(periodo_habilitado_clase_suelta(self.junio, hoy))
        self.assertFalse(requiere_precola_suelta(self.junio, hoy))

    def test_vencimiento_mensual_alcanzado_despues_del_dia_10(self):
        self.assertFalse(vencimiento_mensual_alcanzado(self.junio, date(2026, 6, 10)))
        self.assertTrue(vencimiento_mensual_alcanzado(self.junio, date(2026, 6, 11)))

    @override_settings(HABILITAR_PRECOLA_NO_ABONADOS=False)
    def test_precola_deshabilitada_exige_apertura_general(self):
        self.assertFalse(periodo_habilitado_clase_suelta(self.junio, date(2026, 5, 25)))
        self.assertFalse(requiere_precola_suelta(self.junio, date(2026, 5, 25)))
        self.assertTrue(periodo_habilitado_clase_suelta(self.junio, date(2026, 6, 1)))

    @override_settings(DIA_LIMITE_PAGO_MENSUAL=7)
    def test_vencimiento_mensual_configurable_por_setting(self):
        self.assertFalse(vencimiento_mensual_alcanzado(self.junio, date(2026, 6, 7)))
        self.assertTrue(vencimiento_mensual_alcanzado(self.junio, date(2026, 6, 8)))


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
        sede = Sede.objects.create(nombre="Sede Test", direccion="Calle Test")
        sala = Sala.objects.create(nombre="Sala 1", capacidad=20, sede=sede)
        profesor = Teacher.objects.create(nombre="Profe", apellido="Uno")
        self.clase = Class.objects.create(
            disciplina=disciplina,
            sala=sala,
            profesor=profesor,
            dia_semana=1,
            hora_inicio=time(10, 0),
            duracion=timedelta(hours=1),
            cupo_maximo=10,
            estado="disponible",
        )

    @patch("django.utils.timezone.now")
    def test_lista_ocurrencias_en_ventana(self, mock_now):
        hoy = date(2026, 5, 11)
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 5, 11, 9, 0), timezone.get_current_timezone()
        )
        ocurrencias = ocurrencias_clase_en_ventana(
            self.clase, dias=21, desde_fecha=hoy
        )
        self.assertGreaterEqual(len(ocurrencias), 2)
        fechas = [timezone.localdate(dt) for dt, _ in ocurrencias]
        self.assertTrue(all(f >= hoy for f in fechas))
        self.assertTrue(all(f <= hoy + timedelta(days=21) for f in fechas))


class CrearSiguientePeriodoTaskTests(TestCase):
    def setUp(self):
        from apps.classes.models import Disciplina, Sala, Sede, Teacher, Class
        from apps.payments.models import PrecioClase
        
        self.disciplina = Disciplina.objects.create(nombre="Yoga")
        self.sede = Sede.objects.create(nombre="Sede 1", direccion="Direccion 1")
        self.sala = Sala.objects.create(nombre="Sala 1", capacidad=20, sede=self.sede)
        self.teacher = Teacher.objects.create(nombre="Profe", apellido="Uno")
        self.clase = Class.objects.create(
            disciplina=self.disciplina,
            sala=self.sala,
            profesor=self.teacher,
            dia_semana=1,
            hora_inicio=time(10, 0),
            duracion=timedelta(hours=1),
            cupo_maximo=10,
        )
        
        self.periodo_mayo = PeriodoCobro.objects.create(
            nombre="Mayo 2026",
            fecha_inicio_periodo=date(2026, 5, 1),
            fecha_fin_periodo=date(2026, 5, 31),
            apertura_abonados=date(2026, 4, 20),
            apertura_general=date(2026, 5, 1),
        )
        PrecioClase.objects.create(
            clase=self.clase,
            periodo=self.periodo_mayo,
            monto=1000
        )

    @patch("django.utils.timezone.localdate")
    def test_crea_siguiente_periodo_dentro_del_margen(self, mock_localdate):
        from apps.payments.tasks import crear_siguiente_periodo_si_es_necesario
        from apps.payments.models import PrecioClase
        
        # 15 days before June 1 is May 17. 
        # If today is May 17, it should create June.
        mock_localdate.return_value = date(2026, 5, 17)
        crear_siguiente_periodo_si_es_necesario()
        
        self.assertTrue(PeriodoCobro.objects.filter(nombre="Junio 2026").exists())
        periodo_junio = PeriodoCobro.objects.get(nombre="Junio 2026")
        
        self.assertEqual(periodo_junio.fecha_inicio_periodo, date(2026, 6, 1))
        
        # Check prices are copied
        precio_junio = PrecioClase.objects.filter(periodo=periodo_junio, clase=self.clase).first()
        self.assertIsNotNone(precio_junio)
        self.assertEqual(precio_junio.monto, 1000)

    @patch("django.utils.timezone.localdate")
    def test_no_crea_periodo_antes_del_margen(self, mock_localdate):
        from apps.payments.tasks import crear_siguiente_periodo_si_es_necesario
        
        # 16 days before June 1 is May 16. Should not create.
        mock_localdate.return_value = date(2026, 5, 16)
        crear_siguiente_periodo_si_es_necesario()
        
        self.assertFalse(PeriodoCobro.objects.filter(nombre="Junio 2026").exists())
