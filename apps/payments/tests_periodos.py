from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone

from apps.classes.models import Class, Inscripcion
from apps.classes.services import ocurrencias_clase_en_ventana
from apps.payments.models import PeriodoCobro
from apps.payments.periodos import (
    clases_renovables_abonado,
    domingo_semana_iso,
    en_ventana_preinscripcion_abonados,
    es_abonado,
    horizonte_clase_suelta,
    periodo_conteniendo_fecha,
    periodo_habilitado_clase_suelta,
    periodos_elegibles_clase_suelta,
    periodos_elegibles_mensual,
    requiere_precola_suelta,
    vencimiento_mensual_alcanzado,
)

User = get_user_model()


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

    def test_mensual_sin_usuario_solo_devuelve_vigente(self):
        hoy = date(2026, 5, 25)
        nombres = [p.nombre for p in periodos_elegibles_mensual(hoy)]
        self.assertEqual(nombres, ["Mayo 2026"])

    def test_mensual_no_abonado_no_ve_siguiente_en_ventana_abonados(self):
        no_abonado = User.objects.create_user(
            username="noabonado@test.com",
            email="noabonado@test.com",
            password="testpassword123",
            dni="99999990",
            telefono_emergencia="3510009999",
        )
        hoy = date(2026, 5, 25)
        nombres = [p.nombre for p in periodos_elegibles_mensual(hoy, usuario=no_abonado)]
        self.assertEqual(nombres, ["Mayo 2026"])

    def test_clase_suelta_periodos_en_semana_iso(self):
        # 25/5/2026 = Lunes. La semana ISO va hasta el domingo 31/5.
        hoy = date(2026, 5, 25)
        elegibles = periodos_elegibles_clase_suelta(hoy)
        nombres = [p.nombre for p in elegibles]
        self.assertEqual(nombres, ["Mayo 2026"])

    def test_horizonte_es_domingo_de_la_semana_iso(self):
        # Jueves 28/5/2026 → domingo 31/5/2026.
        self.assertEqual(horizonte_clase_suelta(date(2026, 5, 28)), date(2026, 5, 31))
        # Lunes 1/6/2026 → domingo 7/6/2026.
        self.assertEqual(horizonte_clase_suelta(date(2026, 6, 1)), date(2026, 6, 7))

    def test_domingo_semana_iso(self):
        self.assertEqual(domingo_semana_iso(date(2026, 5, 25)), date(2026, 5, 31))
        self.assertEqual(domingo_semana_iso(date(2026, 5, 31)), date(2026, 5, 31))
        self.assertEqual(domingo_semana_iso(date(2026, 6, 1)), date(2026, 6, 7))

    @override_settings(VENTANA_OCURRENCIAS_CLASE_SUELTA_DIAS=21)
    def test_override_admin_extiende_horizonte_clase_suelta(self):
        hoy = date(2026, 5, 25)
        # Con override 21 días, junio entra de nuevo.
        nombres = [p.nombre for p in periodos_elegibles_clase_suelta(hoy)]
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


class AbonadoYRenovacionTests(TestCase):
    """Reglas del 'beneficio del abonado': pre-inscripción solo para renovar.

    Modelo:
    - Abonado = tiene MENSUAL activa (RESERVADA o PENDIENTE_PAGO) en vigente.
    - En la ventana de abonados [apertura_abonados, fecha_inicio): solo el abonado
      puede pre-inscribirse al próximo período, y SOLO para renovar las clases
      que ya tiene activas en vigente (no a otras clases).
    """

    def setUp(self):
        from apps.classes.models import Disciplina, Sala, Sede, Teacher

        self.mayo = PeriodoCobro.objects.create(
            nombre="Mayo 2026",
            fecha_inicio_periodo=date(2026, 5, 1),
            fecha_fin_periodo=date(2026, 5, 31),
            apertura_abonados=date(2026, 4, 20),
            apertura_general=date(2026, 5, 1),
        )
        self.junio = PeriodoCobro.objects.create(
            nombre="Junio 2026",
            fecha_inicio_periodo=date(2026, 6, 1),
            fecha_fin_periodo=date(2026, 6, 30),
            apertura_abonados=date(2026, 5, 20),
            apertura_general=date(2026, 6, 1),
        )

        disc = Disciplina.objects.create(nombre="Yoga")
        sede = Sede.objects.create(nombre="Sede", direccion="C 1")
        sala = Sala.objects.create(nombre="Sala 1", capacidad=20, sede=sede)
        profesor = Teacher.objects.create(nombre="P", apellido="A")
        self.clase_propia = Class.objects.create(
            disciplina=disc, sala=sala, profesor=profesor,
            dia_semana=0, hora_inicio=time(10, 0),
            duracion=timedelta(hours=1), cupo_maximo=10, estado="disponible",
        )
        self.clase_otra = Class.objects.create(
            disciplina=disc, sala=sala, profesor=profesor,
            dia_semana=2, hora_inicio=time(18, 0),
            duracion=timedelta(hours=1), cupo_maximo=10, estado="disponible",
        )

        self.abonado = User.objects.create_user(
            username="abonado@test.com", email="abonado@test.com",
            password="testpassword123", dni="55555555",
            telefono_emergencia="3510000005",
        )
        self.no_abonado = User.objects.create_user(
            username="noabonado2@test.com", email="noabonado2@test.com",
            password="testpassword123", dni="66666666",
            telefono_emergencia="3510000006",
        )
        Inscripcion.objects.create(
            usuario=self.abonado, clase=self.clase_propia, periodo=self.mayo,
            tipo=Inscripcion.Tipo.MENSUAL, estado=Inscripcion.Estado.RESERVADA,
        )

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 25))
    def test_es_abonado_true_si_mensual_activa_en_vigente(self, _):
        self.assertTrue(es_abonado(self.abonado))
        self.assertFalse(es_abonado(self.no_abonado))

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 25))
    def test_es_abonado_ignora_canceladas(self, _):
        Inscripcion.objects.filter(usuario=self.abonado).update(
            estado=Inscripcion.Estado.CANCELADA
        )
        self.assertFalse(es_abonado(self.abonado))

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 25))
    def test_clases_renovables_son_las_del_abonado_en_vigente(self, _):
        renovables = clases_renovables_abonado(self.abonado)
        self.assertEqual(renovables, {self.clase_propia.id})
        self.assertEqual(clases_renovables_abonado(self.no_abonado), set())

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 25))
    def test_abonado_ve_siguiente_en_ventana_pre_inscripcion(self, _):
        nombres = [p.nombre for p in periodos_elegibles_mensual(usuario=self.abonado)]
        self.assertEqual(nombres, ["Mayo 2026", "Junio 2026"])

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 25))
    def test_no_abonado_no_ve_siguiente_aunque_este_en_ventana(self, _):
        nombres = [p.nombre for p in periodos_elegibles_mensual(usuario=self.no_abonado)]
        self.assertEqual(nombres, ["Mayo 2026"])

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 18))
    def test_abonado_fuera_de_ventana_no_ve_siguiente(self, _):
        # 18/5 < apertura_abonados (20/5) y < apertura_abonados global (-10 días = 22/5)
        nombres = [p.nombre for p in periodos_elegibles_mensual(usuario=self.abonado)]
        self.assertEqual(nombres, ["Mayo 2026"])

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 25))
    def test_validar_intencion_rechaza_clase_no_renovable_para_abonado(self, _):
        """Aunque sea abonado, no puede pre-inscribirse a una clase que no tiene."""
        from apps.classes.exceptions import ReservaError
        from apps.classes.services import validar_intencion_inscripcion

        with self.assertRaisesMessage(
            ReservaError, "Solo podés renovar al próximo mes las clases"
        ):
            validar_intencion_inscripcion(
                self.abonado, self.clase_otra.id, self.junio,
                Inscripcion.Tipo.MENSUAL,
            )

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 25))
    def test_validar_intencion_rechaza_pre_inscripcion_no_abonado(self, _):
        from apps.classes.exceptions import ReservaError
        from apps.classes.services import validar_intencion_inscripcion

        with self.assertRaisesMessage(
            ReservaError, "pre-inscripción al próximo mes es solo para abonados"
        ):
            validar_intencion_inscripcion(
                self.no_abonado, self.clase_propia.id, self.junio,
                Inscripcion.Tipo.MENSUAL,
            )

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 25))
    def test_validar_intencion_acepta_renovacion_de_abonado(self, _):
        from apps.classes.services import validar_intencion_inscripcion

        clase, tipo = validar_intencion_inscripcion(
            self.abonado, self.clase_propia.id, self.junio,
            Inscripcion.Tipo.MENSUAL,
        )
        self.assertEqual(clase.id, self.clase_propia.id)
        self.assertEqual(tipo, Inscripcion.Tipo.MENSUAL)
