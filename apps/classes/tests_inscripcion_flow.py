from datetime import date, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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
        self.periodo = PeriodoCobro.objects.create(
            nombre="Mayo 2026",
            fecha_inicio_periodo=date(2026, 5, 1),
            fecha_fin_periodo=date(2026, 5, 31),
            apertura_abonados=date(2026, 4, 15),
            apertura_general=date(2026, 5, 1),
        )
        disciplina = Disciplina.objects.create(nombre="Funcional")
        sede = Sede.objects.create(nombre="Sede", direccion="Calle 1")
        sala = Sala.objects.create(nombre="Sala", capacidad=20, sede=sede)
        profesor = Teacher.objects.create(nombre="Ana", apellido="Test")
        self.clase = Class.objects.create(
            disciplina=disciplina,
            sala=sala,
            profesor=profesor,
            dia_semana=4,
            hora_inicio=time(18, 0),
            duracion=timedelta(hours=1),
            cupo_maximo=10,
            estado="disponible",
        )
        self.client.force_login(self.user)

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 10))
    def test_post_mensual_guarda_intencion_y_redirige_a_pago(self, _localdate):
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

    @patch("django.utils.timezone.localdate", return_value=date(2026, 5, 10))
    def test_seleccion_pago_mensual_muestra_resumen(self, _localdate):
        self.client.post(
            reverse("classes:inscribir", args=[self.clase.id]),
            {"tipo": Inscripcion.Tipo.MENSUAL, "periodo_id": self.periodo.id},
        )
        response = self.client.get(
            reverse("payments:seleccion_pago_clase", args=[self.clase.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resumen del mes")


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
