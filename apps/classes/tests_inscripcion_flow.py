from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.classes.cliente import periodos_inscripcion_para_clase
from apps.classes.models import Class, Disciplina, Inscripcion, Sala, Sede, Teacher
from apps.classes.services import clases_mensuales_cobrables, validar_intencion_inscripcion
from apps.classes.exceptions import ReservaError
from apps.payments.inscripcion_pago import PAGO_PENDIENTE_SESSION, resumen_abono_para_clase
from apps.payments.models import PeriodoCobro

User = get_user_model()


class InscripcionMensualFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="mensual@test.com",
            email="mensual@test.com",
            password="testpassword123",
            dni="12345678",
            telefono_emergencia="3515550000",
        )
        tz = timezone.get_current_timezone()
        ahora = timezone.now()
        hoy = ahora.date()

        self.periodo = PeriodoCobro.objects.create(
            nombre="Mes Test",
            fecha_inicio_periodo=hoy.replace(day=1),
            fecha_fin_periodo=(hoy.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1),
            apertura_abonados=hoy.replace(day=1) - timedelta(days=15),
            apertura_general=hoy.replace(day=1),
        )
        self.disciplina = Disciplina.objects.create(nombre="Funcional")
        sede = Sede.objects.create(nombre="Sede", direccion="Calle 1")
        sala = Sala.objects.create(nombre="Sala", capacidad=20, sede=sede)
        profesor = Teacher.objects.create(nombre="Ana", apellido="Test")
        
        dia_semana_test = (hoy.weekday() + 1) % 7 # Mañana
        
        self.clase = Class.objects.create(
            disciplina=self.disciplina,
            sala=sala,
            profesor=profesor,
            dia_semana=dia_semana_test,
            hora_inicio=time(18, 0),
            duracion=timedelta(hours=1),
            cupo_maximo=10,
            estado="disponible",
        )
        self.client.force_login(self.user)

    # @patch ya no es necesario si las fechas son relativas al dia de hoy, 
    # pero si lo quitamos tenemos que sacarle los argumentos a las funciones.
    def test_post_mensual_guarda_intencion_y_redirige_a_pago(self):
        url = reverse("classes:inscribir", args=[self.clase.id])
        response = self.client.post(
            url,
            {"tipo": Inscripcion.Tipo.MENSUAL, "periodo_id": self.periodo.id},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("payments:seleccion_pago_clase", args=[self.clase.id]),
        )
        data = self.client.session[PAGO_PENDIENTE_SESSION]
        self.assertEqual(data["clase_id"], self.clase.id)
        self.assertEqual(data["tipo"], Inscripcion.Tipo.MENSUAL)
        self.assertEqual(data["periodo_id"], self.periodo.id)

    def test_seleccion_pago_mensual_muestra_resumen(self):
        self.client.post(
            reverse("classes:inscribir", args=[self.clase.id]),
            {"tipo": Inscripcion.Tipo.MENSUAL, "periodo_id": self.periodo.id},
        )
        response = self.client.get(
            reverse("payments:seleccion_pago_clase", args=[self.clase.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resumen")


class InscripcionMensualSinClasesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sincclases@test.com",
            email="sincclases@test.com",
            password="testpassword123",
            dni="87654321",
            telefono_emergencia="3515551111",
        )
        self.periodo = PeriodoCobro.objects.create(
            nombre="Mayo 2026",
            fecha_inicio_periodo=date(2026, 5, 1),
            fecha_fin_periodo=date(2026, 5, 31),
            apertura_abonados=date(2026, 4, 15),
            apertura_general=date(2026, 5, 1),
        )
        disciplina = Disciplina.objects.create(nombre="Yoga")
        sede = Sede.objects.create(nombre="Sede", direccion="Calle 2")
        sala = Sala.objects.create(nombre="Sala", capacidad=20, sede=sede)
        profesor = Teacher.objects.create(nombre="Lu", apellido="Test")
        self.clase = Class.objects.create(
            disciplina=disciplina,
            sala=sala,
            profesor=profesor,
            dia_semana=0,
            hora_inicio=time(10, 0),
            duracion=timedelta(hours=1),
            cupo_maximo=10,
            estado="disponible",
        )
        self.client.force_login(self.user)
        self.hoy = date(2026, 5, 29)

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 29))
    def test_sin_clases_restantes_no_ofrece_periodo_mensual(self, _localdate):
        data = periodos_inscripcion_para_clase(self.clase)
        self.assertEqual(data["MENSUAL"], [])

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 29))
    def test_validar_intencion_rechaza_mensual_sin_clases(self, _localdate):
        self.assertEqual(
            clases_mensuales_cobrables(self.clase, self.periodo, self.hoy), 0
        )
        with self.assertRaisesMessage(
            ReservaError, "No quedan clases de este horario en el mes elegido."
        ):
            validar_intencion_inscripcion(
                self.user,
                self.clase.id,
                self.periodo,
                Inscripcion.Tipo.MENSUAL,
            )

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 29))
    def test_resumen_abono_none_si_no_hay_clases(self, _localdate):
        self.assertIsNone(
            resumen_abono_para_clase(
                self.clase, self.periodo, Inscripcion.Tipo.MENSUAL
            )
        )

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 29))
    def test_post_mensual_sin_clases_vuelve_al_detalle(self, _localdate):
        response = self.client.post(
            reverse("classes:inscribir", args=[self.clase.id]),
            {"tipo": Inscripcion.Tipo.MENSUAL, "periodo_id": self.periodo.id},
        )
        self.assertRedirects(
            response,
            reverse("classes:detalle", args=[self.clase.id]),
        )
        self.assertNotIn(PAGO_PENDIENTE_SESSION, self.client.session)


class InscripcionSueltaPrioridadFlowTests(TestCase):
    """Pre-cola en boundary Junio→Julio (julio empieza miércoles 1/7/2026).

    La semana ISO Lun 29/6 – Dom 5/7 abarca el cambio de período, lo que nos
    permite testear pre-cola para una fecha de julio estando aún en junio.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="sueltaflow@test.com",
            email="sueltaflow@test.com",
            password="testpassword123",
            dni="11223344",
            telefono_emergencia="3515552222",
        )
        self.junio = PeriodoCobro.objects.create(
            nombre="Junio 2026",
            fecha_inicio_periodo=date(2026, 6, 1),
            fecha_fin_periodo=date(2026, 6, 30),
            apertura_abonados=date(2026, 5, 20),
            apertura_general=date(2026, 6, 1),
        )
        self.julio = PeriodoCobro.objects.create(
            nombre="Julio 2026",
            fecha_inicio_periodo=date(2026, 7, 1),
            fecha_fin_periodo=date(2026, 7, 31),
            apertura_abonados=date(2026, 6, 21),
            apertura_general=date(2026, 7, 1),
        )
        disciplina = Disciplina.objects.create(nombre="Spinning")
        sede = Sede.objects.create(nombre="Sede Spinning", direccion="Calle 3")
        sala = Sala.objects.create(nombre="Sala Spin", capacidad=20, sede=sede)
        profesor = Teacher.objects.create(nombre="Pepe", apellido="Spin")
        self.clase = Class.objects.create(
            disciplina=disciplina,
            sala=sala,
            profesor=profesor,
            dia_semana=2,  # Miércoles → cae 1/7/2026 en la semana ISO
            hora_inicio=time(10, 0),
            duracion=timedelta(hours=1),
            cupo_maximo=5,
            estado="disponible",
        )
        self.client.force_login(self.user)

    def _fecha_iso_julio(self, ahora):
        from apps.classes.services import ocurrencias_clase_en_ventana

        ocurrencias = ocurrencias_clase_en_ventana(self.clase, desde_fecha=ahora.date())
        for dt, periodo in ocurrencias:
            if periodo.id == self.julio.id:
                return dt.isoformat()
        self.fail("No se encontró ocurrencia de julio en la ventana ISO.")

    @override_settings(HABILITAR_PRECOLA_NO_ABONADOS=True)
    @patch("django.utils.timezone.localdate")
    @patch("django.utils.timezone.now")
    def test_precola_suelta_desde_inscribir_crea_espera(self, mock_now, mock_localdate):
        # Lunes 29/6/2026: semana ISO 29/6–5/7 cruza a julio.
        ahora = timezone.make_aware(
            datetime(2026, 6, 29, 9, 0), timezone.get_current_timezone()
        )
        mock_now.return_value = ahora
        def _localdate_side_effect(value=None, timezone=None):
            if value is None:
                return date(2026, 6, 29)
            return value.date()

        mock_localdate.side_effect = _localdate_side_effect
        response = self.client.post(
            reverse("classes:inscribir", args=[self.clase.id]),
            {
                "tipo": Inscripcion.Tipo.CLASE_SUELTA,
                "fecha_clase": self._fecha_iso_julio(ahora),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("classes:detalle", args=[self.clase.id]))
        inscripcion = Inscripcion.objects.get(usuario=self.user, clase=self.clase)
        self.assertEqual(inscripcion.tipo, Inscripcion.Tipo.CLASE_SUELTA)
        self.assertEqual(inscripcion.estado, Inscripcion.Estado.ESPERA)

    @patch("django.utils.timezone.localdate")
    @patch("django.utils.timezone.now")
    def test_suelta_desde_dia_uno_redirige_a_pago_si_hay_cupo(self, mock_now, mock_localdate):
        # Miércoles 1/7/2026: apertura_general de julio → reserva directa.
        ahora = timezone.make_aware(
            datetime(2026, 7, 1, 9, 0), timezone.get_current_timezone()
        )
        mock_now.return_value = ahora
        def _localdate_side_effect(value=None, timezone=None):
            if value is None:
                return date(2026, 7, 1)
            return value.date()

        mock_localdate.side_effect = _localdate_side_effect
        # La sesión se creó con el now real (~jun/2026); como mockeamos al
        # 1/7/2026, Django la ve expirada. Re-login bajo el now mockeado.
        self.client.force_login(self.user)
        # La clase es a las 10:00 del 1/7 (después de las 9:00 del mock).
        from apps.classes.services import ocurrencias_clase_en_ventana

        ocurrencias = ocurrencias_clase_en_ventana(self.clase, desde_fecha=ahora.date())
        fecha_iso = next(
            dt.isoformat() for dt, p in ocurrencias if p.id == self.julio.id
        )
        response = self.client.post(
            reverse("classes:inscribir", args=[self.clase.id]),
            {
                "tipo": Inscripcion.Tipo.CLASE_SUELTA,
                "fecha_clase": fecha_iso,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, reverse("payments:seleccion_pago_clase", args=[self.clase.id])
        )
