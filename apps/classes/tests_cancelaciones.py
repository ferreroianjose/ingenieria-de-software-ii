from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.classes.models import Class, Disciplina, Inscripcion, InscripcionOcurrencia, Sala, Sede, Teacher
from apps.classes.ocurrencias import crear_ocurrencia_suelta, generar_ocurrencias_mensual
from apps.classes.services import cancelar_ocurrencia_mensual, cancelar_reserva
from apps.classes.exceptions import CancelacionMensualNoPermitida, OcurrenciaYaCancelada
from apps.payments.models import Credito, Pago, PagoInscripcion, PeriodoCobro, PrecioDisciplina
from apps.payments.inscripcion_pago import PAGO_PENDIENTE_SESSION, monto_sena, precio_base_inscripcion

User = get_user_model()


class CancelacionesTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="cancel@test.com",
            email="cancel@test.com",
            password="testpassword123",
            dni="11223344",
            telefono_emergencia="3515559999",
        )
        self.periodo = PeriodoCobro.objects.create(
            nombre="Mayo 2026",
            fecha_inicio_periodo=date(2026, 5, 1),
            fecha_fin_periodo=date(2026, 5, 31),
            apertura_abonados=date(2026, 4, 15),
            apertura_general=date(2026, 5, 1),
        )
        self.disciplina = Disciplina.objects.create(nombre="Yoga")
        PrecioDisciplina.objects.create(
            disciplina=self.disciplina,
            periodo=self.periodo,
            monto=Decimal("3000.00"),
        )
        sede = Sede.objects.create(nombre="Central", direccion="Calle 1")
        sala = Sala.objects.create(nombre="Sala A", capacidad=10, sede=sede)
        profesor = Teacher.objects.create(nombre="Ana", apellido="Pro")
        self.clase = Class.objects.create(
            disciplina=self.disciplina,
            sala=sala,
            profesor=profesor,
            dia_semana=4,
            hora_inicio=time(18, 0),
            duracion=timedelta(hours=1),
            cupo_maximo=10,
            estado="disponible",
        )
        tz = timezone.get_current_timezone()
        self.fecha_mensual = timezone.make_aware(
            datetime(2026, 5, 15, 18, 0), tz
        )
        self.fecha_suelta = timezone.make_aware(
            datetime(2026, 5, 22, 18, 0), tz
        )

    def _inscripcion_mensual(self):
        inscripcion = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.MENSUAL,
            estado=Inscripcion.Estado.RESERVADA,
        )
        generar_ocurrencias_mensual(inscripcion)
        return inscripcion

    def _inscripcion_suelta(self, estado=Inscripcion.Estado.RESERVADA):
        inscripcion = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=estado,
        )
        crear_ocurrencia_suelta(inscripcion, self.fecha_suelta)
        return inscripcion

    def test_ocurrencias_reserva_ui_suelta_muestra_cancelar(self):
        from apps.classes.ocurrencias import ocurrencias_reserva_ui

        inscripcion = self._inscripcion_suelta()
        filas = ocurrencias_reserva_ui(inscripcion)

        self.assertEqual(len(filas), 1)
        self.assertTrue(filas[0]["puede_cancelar"])

    def test_ocurrencias_reserva_ui_suelta_impaga_no_muestra_cancelar_en_fila(self):
        from apps.classes.ocurrencias import ocurrencias_reserva_ui

        inscripcion = self._inscripcion_suelta(estado=Inscripcion.Estado.PENDIENTE_PAGO)
        filas = ocurrencias_reserva_ui(inscripcion)

        self.assertEqual(len(filas), 1)
        self.assertFalse(filas[0]["puede_cancelar"])

    def test_ocurrencias_reserva_ui_mensual_impaga_no_muestra_cancelar_en_fila(self):
        from apps.classes.ocurrencias import ocurrencias_reserva_ui

        inscripcion = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.MENSUAL,
            estado=Inscripcion.Estado.PENDIENTE_PAGO,
        )
        filas = ocurrencias_reserva_ui(inscripcion)

        self.assertFalse(any(fila["puede_cancelar"] for fila in filas))

    def test_cancelar_reserva_mensual_impaga(self):
        inscripcion = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.MENSUAL,
            estado=Inscripcion.Estado.PENDIENTE_PAGO,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("classes:cancelar_reserva", args=[inscripcion.id]),
        )

        self.assertRedirects(response, reverse("classes:mis_reservas"))
        inscripcion.refresh_from_db()
        self.assertEqual(inscripcion.estado, Inscripcion.Estado.CANCELADA)

    def test_ocurrencias_reserva_ui_mensual_muestra_cancelar_por_clase(self):
        from apps.classes.ocurrencias import ocurrencias_reserva_ui

        inscripcion = self._inscripcion_mensual()
        filas = ocurrencias_reserva_ui(inscripcion)

        self.assertGreater(len(filas), 0)
        self.assertTrue(any(fila["puede_cancelar"] for fila in filas))

    @patch("django.utils.timezone.now")
    def test_cancelar_ocurrencia_mensual_otorga_credito_con_48h(self, mock_now):
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 5, 13, 10, 0), timezone.get_current_timezone()
        )
        inscripcion = self._inscripcion_mensual()

        resultado = cancelar_ocurrencia_mensual(
            inscripcion.id, self.user, self.fecha_mensual
        )

        self.assertTrue(resultado.otorga_credito)
        inscripcion.refresh_from_db()
        self.assertEqual(inscripcion.estado, Inscripcion.Estado.RESERVADA)
        self.assertEqual(Credito.objects.filter(usuario=self.user).count(), 1)
        ocurrencia = InscripcionOcurrencia.objects.get(
            inscripcion=inscripcion, fecha_clase=self.fecha_mensual
        )
        self.assertEqual(ocurrencia.estado, InscripcionOcurrencia.Estado.CANCELADA)
        self.assertTrue(ocurrencia.otorga_credito)
        self.assertIsNotNone(ocurrencia.credito)

    @patch("django.utils.timezone.now")
    def test_cancelar_ocurrencia_mensual_sin_credito_dentro_de_48h(self, mock_now):
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 5, 14, 20, 0), timezone.get_current_timezone()
        )
        inscripcion = self._inscripcion_mensual()

        resultado = cancelar_ocurrencia_mensual(
            inscripcion.id, self.user, self.fecha_mensual
        )

        self.assertFalse(resultado.otorga_credito)
        self.assertEqual(Credito.objects.count(), 0)
        ocurrencia = InscripcionOcurrencia.objects.get(
            inscripcion=inscripcion, fecha_clase=self.fecha_mensual
        )
        self.assertEqual(ocurrencia.estado, InscripcionOcurrencia.Estado.CANCELADA)
        self.assertFalse(ocurrencia.otorga_credito)
        self.assertIsNone(ocurrencia.credito)

    @patch("django.utils.timezone.now")
    def test_no_cancelar_ocurrencia_duplicada(self, mock_now):
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 5, 10, 10, 0), timezone.get_current_timezone()
        )
        inscripcion = self._inscripcion_mensual()
        cancelar_ocurrencia_mensual(inscripcion.id, self.user, self.fecha_mensual)

        with self.assertRaises(OcurrenciaYaCancelada):
            cancelar_ocurrencia_mensual(
                inscripcion.id, self.user, self.fecha_mensual
            )

    @patch("django.utils.timezone.now")
    def test_no_cancelar_mensual_completa(self, mock_now):
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 5, 10, 10, 0), timezone.get_current_timezone()
        )
        inscripcion = self._inscripcion_mensual()

        with self.assertRaises(CancelacionMensualNoPermitida):
            cancelar_reserva(inscripcion.id, self.user)

    @patch("django.utils.timezone.now")
    def test_cancelar_clase_suelta_reintegra_con_24h(self, mock_now):
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 5, 18, 10, 0), timezone.get_current_timezone()
        )
        inscripcion = self._inscripcion_suelta()
        base = precio_base_inscripcion(inscripcion)
        pago = Pago.objects.create(
            usuario=self.user,
            periodo=self.periodo,
            monto=monto_sena(base),
            metodo=Pago.Metodo.MERCADOPAGO,
            estado=Pago.Estado.COMPLETADO,
        )
        PagoInscripcion.objects.create(
            pago=pago, inscripcion=inscripcion, monto_aplicado=monto_sena(base)
        )

        resultado = cancelar_reserva(inscripcion.id, self.user)

        self.assertTrue(resultado.reembolsado)
        inscripcion.refresh_from_db()
        self.assertEqual(inscripcion.estado, Inscripcion.Estado.CANCELADA)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.REEMBOLSADO)
        ocurrencia = InscripcionOcurrencia.objects.get(inscripcion=inscripcion)
        self.assertEqual(ocurrencia.estado, InscripcionOcurrencia.Estado.CANCELADA)

    @patch("django.utils.timezone.now")
    def test_cancelar_clase_suelta_retiene_sena_dentro_de_24h(self, mock_now):
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 5, 22, 10, 0), timezone.get_current_timezone()
        )
        inscripcion = self._inscripcion_suelta()
        base = precio_base_inscripcion(inscripcion)
        pago = Pago.objects.create(
            usuario=self.user,
            periodo=self.periodo,
            monto=monto_sena(base),
            metodo=Pago.Metodo.MERCADOPAGO,
            estado=Pago.Estado.COMPLETADO,
        )
        PagoInscripcion.objects.create(
            pago=pago, inscripcion=inscripcion, monto_aplicado=monto_sena(base)
        )

        resultado = cancelar_reserva(inscripcion.id, self.user)

        self.assertFalse(resultado.reembolsado)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.Estado.COMPLETADO)

    @patch("django.utils.timezone.now")
    def test_vista_cancelar_ocurrencia_mensual(self, mock_now):
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 5, 10, 10, 0), timezone.get_current_timezone()
        )
        inscripcion = self._inscripcion_mensual()
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("classes:cancelar_ocurrencia", args=[inscripcion.id]),
            {"fecha_clase": self.fecha_mensual.isoformat()},
        )

        self.assertRedirects(response, reverse("classes:mis_reservas"))
        self.assertEqual(Credito.objects.filter(usuario=self.user).count(), 1)

    @patch("django.utils.timezone.now")
    def test_pagar_clase_individual_con_credito(self, mock_now):
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 5, 10, 10, 0), timezone.get_current_timezone()
        )
        Credito.objects.create(
            usuario=self.user,
            periodo=self.periodo,
            disciplina=self.disciplina,
            estado=Credito.Estado.DISPONIBLE,
        )
        self.client.force_login(self.user)
        session = self.client.session
        session[PAGO_PENDIENTE_SESSION] = {
            "clase_id": self.clase.id,
            "periodo_id": self.periodo.id,
            "tipo": Inscripcion.Tipo.CLASE_SUELTA,
            "fecha_clase": self.fecha_suelta.isoformat(),
        }
        session.save()

        response = self.client.post(
            reverse("payments:pagar_clase", args=[self.clase.id]),
            {"modalidad": "TOTAL"},
        )

        self.assertRedirects(response, reverse("classes:mis_reservas"))
        inscripcion = Inscripcion.objects.get(
            usuario=self.user, clase=self.clase, tipo=Inscripcion.Tipo.CLASE_SUELTA
        )
        self.assertEqual(inscripcion.estado, Inscripcion.Estado.RESERVADA)
        self.assertTrue(inscripcion.ocurrencias.filter(estado="ACTIVA").exists())
        self.assertEqual(
            Credito.objects.get(usuario=self.user).estado, Credito.Estado.UTILIZADO
        )
        self.assertTrue(
            Pago.objects.filter(
                usuario=self.user, metodo=Pago.Metodo.CREDITO, estado=Pago.Estado.COMPLETADO
            ).exists()
        )

    @patch("django.utils.timezone.now")
    def test_credito_automatico_cubre_saldo_pendiente(self, mock_now):
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 5, 10, 10, 0), timezone.get_current_timezone()
        )
        Credito.objects.create(
            usuario=self.user,
            periodo=self.periodo,
            disciplina=self.disciplina,
            estado=Credito.Estado.DISPONIBLE,
        )
        inscripcion = self._inscripcion_suelta(estado=Inscripcion.Estado.PENDIENTE_PAGO)
        sena = precio_base_inscripcion(inscripcion) / 2
        pago = Pago.objects.create(
            usuario=self.user,
            periodo=self.periodo,
            monto=sena,
            metodo=Pago.Metodo.MERCADOPAGO,
            estado=Pago.Estado.COMPLETADO,
        )
        PagoInscripcion.objects.create(
            pago=pago, inscripcion=inscripcion, monto_aplicado=sena
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("payments:pagar", args=[inscripcion.id]),
            {"modalidad": "SALDO"},
        )

        self.assertRedirects(response, reverse("classes:mis_reservas"))
        inscripcion.refresh_from_db()
        self.assertEqual(inscripcion.estado, Inscripcion.Estado.RESERVADA)
        self.assertEqual(
            Credito.objects.get(usuario=self.user).estado, Credito.Estado.UTILIZADO
        )

    @patch("django.utils.timezone.now")
    def test_creditos_disponibles_cuenta_todos_los_periodos(self, mock_now):
        from apps.payments.creditos import creditos_disponibles_count

        mock_now.return_value = timezone.make_aware(
            datetime(2026, 5, 13, 10, 0), timezone.get_current_timezone()
        )
        periodo_junio = PeriodoCobro.objects.create(
            nombre="Junio 2026",
            fecha_inicio_periodo=date(2026, 6, 1),
            fecha_fin_periodo=date(2026, 6, 30),
            apertura_abonados=date(2026, 5, 15),
            apertura_general=date(2026, 6, 1),
        )
        inscripcion = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=periodo_junio,
            tipo=Inscripcion.Tipo.MENSUAL,
            estado=Inscripcion.Estado.RESERVADA,
        )
        InscripcionOcurrencia.objects.create(
            inscripcion=inscripcion,
            fecha_clase=timezone.make_aware(
                datetime(2026, 6, 5, 18, 0), timezone.get_current_timezone()
            ),
            estado=InscripcionOcurrencia.Estado.ACTIVA,
        )
        Credito.objects.create(
            usuario=self.user,
            periodo=periodo_junio,
            disciplina=self.disciplina,
            estado=Credito.Estado.DISPONIBLE,
        )

        self.assertEqual(creditos_disponibles_count(self.user), 1)
        self.assertEqual(
            creditos_disponibles_count(self.user, periodo=self.periodo), 0
        )

    def test_creditos_resumen_disciplina_agrupa_por_periodo(self):
        from apps.payments.creditos import creditos_resumen_disciplina

        periodo_junio = PeriodoCobro.objects.create(
            nombre="Junio 2026",
            fecha_inicio_periodo=date(2026, 6, 1),
            fecha_fin_periodo=date(2026, 6, 30),
            apertura_abonados=date(2026, 5, 15),
            apertura_general=date(2026, 6, 1),
        )
        pilates = Disciplina.objects.create(nombre="Pilates")
        Credito.objects.create(
            usuario=self.user,
            periodo=self.periodo,
            disciplina=self.disciplina,
            estado=Credito.Estado.DISPONIBLE,
        )
        Credito.objects.create(
            usuario=self.user,
            periodo=self.periodo,
            disciplina=self.disciplina,
            estado=Credito.Estado.DISPONIBLE,
        )
        Credito.objects.create(
            usuario=self.user,
            periodo=periodo_junio,
            disciplina=pilates,
            estado=Credito.Estado.DISPONIBLE,
        )

        resumen = creditos_resumen_disciplina(self.user)

        self.assertEqual(len(resumen), 2)
        self.assertEqual(
            resumen[0],
            {
                "disciplina": "Pilates",
                "periodo": "Junio 2026",
                "cantidad": 1,
            },
        )
        self.assertEqual(
            resumen[1],
            {
                "disciplina": "Yoga",
                "periodo": "Mayo 2026",
                "cantidad": 2,
            },
        )
