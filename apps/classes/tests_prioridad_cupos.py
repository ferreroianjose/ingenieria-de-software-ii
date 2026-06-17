from datetime import date, datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.classes.models import Class, Disciplina, Inscripcion, Sala, Sede, Teacher
from apps.classes.services import (
    cancelar_reserva,
    ocurrencias_clase_en_ventana,
    reconciliar_vencimientos_mensuales,
    reservar_clase,
)
from apps.payments.models import PeriodoCobro

User = get_user_model()


class PrioridadYCuposTests(TestCase):
    def setUp(self):
        self.user_reserva = User.objects.create_user(
            username="reserva@test.com",
            email="reserva@test.com",
            password="testpassword123",
            dni="11111111",
            telefono_emergencia="3510000001",
        )
        self.user_mensual = User.objects.create_user(
            username="mensual@test.com",
            email="mensual2@test.com",
            password="testpassword123",
            dni="22222222",
            telefono_emergencia="3510000002",
        )
        self.user_suelta = User.objects.create_user(
            username="suelta@test.com",
            email="suelta@test.com",
            password="testpassword123",
            dni="33333333",
            telefono_emergencia="3510000003",
        )

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
        disciplina = Disciplina.objects.create(nombre="Yoga Prioridad")
        sede = Sede.objects.create(nombre="Sede Prioridad", direccion="Calle 123")
        sala = Sala.objects.create(nombre="Sala Prioridad", capacidad=20, sede=sede)
        profesor = Teacher.objects.create(nombre="Profe", apellido="Prioridad")
        self.clase = Class.objects.create(
            disciplina=disciplina,
            sala=sala,
            profesor=profesor,
            dia_semana=1,  # Martes
            hora_inicio=time(10, 0),
            duracion=timedelta(hours=1),
            cupo_maximo=1,
            estado="disponible",
        )

    def _primer_fecha_junio(self, ahora):
        ocurrencias = ocurrencias_clase_en_ventana(self.clase, desde_fecha=ahora.date())
        for dt, periodo in ocurrencias:
            if periodo.id == self.junio.id:
                return dt
        self.fail("No se encontró ocurrencia de junio en la ventana.")

    @patch("django.utils.timezone.now")
    def test_suelta_en_precola_queda_en_espera_aun_con_cupo(self, mock_now):
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 5, 25, 9, 0), timezone.get_current_timezone()
        )
        fecha_clase = self._primer_fecha_junio(mock_now.return_value)

        inscripcion, resultado = reservar_clase(
            self.user_suelta,
            self.clase.id,
            periodo=self.junio,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            fecha_clase=fecha_clase,
        )

        self.assertEqual(resultado, "espera")
        self.assertEqual(inscripcion.estado, Inscripcion.Estado.ESPERA)

    @patch("django.utils.timezone.now")
    def test_suelta_desde_apertura_general_pasa_a_pendiente_pago(self, mock_now):
        mock_now.return_value = timezone.make_aware(
            datetime(2026, 6, 1, 9, 0), timezone.get_current_timezone()
        )
        fecha_clase = self._primer_fecha_junio(mock_now.return_value)

        inscripcion, resultado = reservar_clase(
            self.user_suelta,
            self.clase.id,
            periodo=self.junio,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            fecha_clase=fecha_clase,
        )

        self.assertEqual(resultado, "pendiente_pago")
        self.assertEqual(inscripcion.estado, Inscripcion.Estado.PENDIENTE_PAGO)

    def test_promocion_espera_prioriza_mensual_antes_que_suelta(self):
        reservada = Inscripcion.objects.create(
            usuario=self.user_reserva,
            clase=self.clase,
            periodo=self.mayo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.RESERVADA,
        )
        espera_suelta = Inscripcion.objects.create(
            usuario=self.user_suelta,
            clase=self.clase,
            periodo=self.mayo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.ESPERA,
        )
        espera_mensual = Inscripcion.objects.create(
            usuario=self.user_mensual,
            clase=self.clase,
            periodo=self.mayo,
            tipo=Inscripcion.Tipo.MENSUAL,
            estado=Inscripcion.Estado.ESPERA,
        )

        cancelar_reserva(reservada.id, self.user_reserva)

        espera_suelta.refresh_from_db()
        espera_mensual.refresh_from_db()
        self.assertEqual(espera_mensual.estado, Inscripcion.Estado.PENDIENTE_PAGO)
        self.assertEqual(espera_suelta.estado, Inscripcion.Estado.ESPERA)

    def test_promocion_espera_respeta_fifo_dentro_de_mensuales(self):
        reservada = Inscripcion.objects.create(
            usuario=self.user_reserva,
            clase=self.clase,
            periodo=self.mayo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.RESERVADA,
        )
        mensual_1 = Inscripcion.objects.create(
            usuario=self.user_mensual,
            clase=self.clase,
            periodo=self.mayo,
            tipo=Inscripcion.Tipo.MENSUAL,
            estado=Inscripcion.Estado.ESPERA,
        )
        mensual_2_user = User.objects.create_user(
            username="mensual3@test.com",
            email="mensual3@test.com",
            password="testpassword123",
            dni="44444444",
            telefono_emergencia="3510000004",
        )
        mensual_2 = Inscripcion.objects.create(
            usuario=mensual_2_user,
            clase=self.clase,
            periodo=self.mayo,
            tipo=Inscripcion.Tipo.MENSUAL,
            estado=Inscripcion.Estado.ESPERA,
        )
        # Fuerza orden FIFO explícito
        mensual_1.fecha_inscripcion = timezone.make_aware(
            datetime(2026, 5, 1, 10, 0), timezone.get_current_timezone()
        )
        mensual_1.save(update_fields=["fecha_inscripcion"])
        mensual_2.fecha_inscripcion = timezone.make_aware(
            datetime(2026, 5, 1, 11, 0), timezone.get_current_timezone()
        )
        mensual_2.save(update_fields=["fecha_inscripcion"])

        cancelar_reserva(reservada.id, self.user_reserva)

        mensual_1.refresh_from_db()
        mensual_2.refresh_from_db()
        self.assertEqual(mensual_1.estado, Inscripcion.Estado.PENDIENTE_PAGO)
        self.assertEqual(mensual_2.estado, Inscripcion.Estado.ESPERA)

    def test_reconciliacion_dia_11_libera_impagos_y_promueve_espera(self):
        mensual_impaga = Inscripcion.objects.create(
            usuario=self.user_mensual,
            clase=self.clase,
            periodo=self.junio,
            tipo=Inscripcion.Tipo.MENSUAL,
            estado=Inscripcion.Estado.PENDIENTE_PAGO,
        )
        suelta_espera = Inscripcion.objects.create(
            usuario=self.user_suelta,
            clase=self.clase,
            periodo=self.junio,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.ESPERA,
        )

        canceladas = reconciliar_vencimientos_mensuales(fecha=date(2026, 6, 11))

        mensual_impaga.refresh_from_db()
        suelta_espera.refresh_from_db()
        self.assertEqual(canceladas, 1)
        self.assertEqual(mensual_impaga.estado, Inscripcion.Estado.CANCELADA)
        self.assertEqual(suelta_espera.estado, Inscripcion.Estado.PENDIENTE_PAGO)

    def test_reconciliacion_no_ejecuta_antes_del_dia_limite(self):
        mensual_impaga = Inscripcion.objects.create(
            usuario=self.user_mensual,
            clase=self.clase,
            periodo=self.junio,
            tipo=Inscripcion.Tipo.MENSUAL,
            estado=Inscripcion.Estado.PENDIENTE_PAGO,
        )
        suelta_espera = Inscripcion.objects.create(
            usuario=self.user_suelta,
            clase=self.clase,
            periodo=self.junio,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.ESPERA,
        )

        canceladas = reconciliar_vencimientos_mensuales(fecha=date(2026, 6, 10))

        mensual_impaga.refresh_from_db()
        suelta_espera.refresh_from_db()
        self.assertEqual(canceladas, 0)
        self.assertEqual(mensual_impaga.estado, Inscripcion.Estado.PENDIENTE_PAGO)
        self.assertEqual(suelta_espera.estado, Inscripcion.Estado.ESPERA)

    def test_reconciliacion_sueltas_cancela_vencidas(self):
        from apps.classes.services import reconciliar_vencimientos_sueltas
        from datetime import timedelta
        from django.test.utils import override_settings
        
        # Una reciente (no debe cancelarse)
        suelta_reciente = Inscripcion.objects.create(
            usuario=self.user_suelta,
            clase=self.clase,
            periodo=self.junio,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.PENDIENTE_PAGO,
        )
        suelta_reciente.fecha_inscripcion = timezone.now() - timedelta(minutes=5)
        suelta_reciente.save(update_fields=['fecha_inscripcion'])

        # Una vencida (debe cancelarse)
        suelta_vencida = Inscripcion.objects.create(
            usuario=self.user_mensual,
            clase=self.clase,
            periodo=self.junio,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.PENDIENTE_PAGO,
        )
        suelta_vencida.fecha_inscripcion = timezone.now() - timedelta(minutes=20)
        suelta_vencida.save(update_fields=['fecha_inscripcion'])

        with override_settings(TIEMPO_GRACIA_PAGO_SUELTO_MINUTOS=15):
            canceladas = reconciliar_vencimientos_sueltas()

        suelta_reciente.refresh_from_db()
        suelta_vencida.refresh_from_db()

        self.assertEqual(canceladas, 1)
        self.assertEqual(suelta_reciente.estado, Inscripcion.Estado.PENDIENTE_PAGO)
        self.assertEqual(suelta_vencida.estado, Inscripcion.Estado.CANCELADA)

    def test_reconciliacion_sueltas_respeta_reservas_con_sena_paga(self):
        """Una reserva con seña paga sobrevive aunque haya pasado el tiempo de gracia."""
        from datetime import timedelta
        from decimal import Decimal

        from django.test.utils import override_settings

        from apps.classes.services import reconciliar_vencimientos_sueltas
        from apps.payments.models import Pago, PagoInscripcion, PrecioClase

        # Precio para que `precio_base_inscripcion` calcule algo sano.
        PrecioClase.objects.get_or_create(
            clase=self.clase, periodo=self.junio, defaults={"monto": Decimal("4000.00")}
        )

        suelta_con_sena = Inscripcion.objects.create(
            usuario=self.user_suelta, clase=self.clase, periodo=self.junio,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.PENDIENTE_PAGO,
        )
        suelta_con_sena.fecha_inscripcion = timezone.now() - timedelta(minutes=40)
        suelta_con_sena.save(update_fields=["fecha_inscripcion"])

        pago_sena = Pago.objects.create(
            usuario=self.user_suelta, periodo=self.junio,
            monto=Decimal("2000.00"), metodo=Pago.Metodo.MERCADOPAGO,
            estado=Pago.Estado.COMPLETADO,
        )
        PagoInscripcion.objects.create(
            pago=pago_sena, inscripcion=suelta_con_sena,
            monto_aplicado=Decimal("2000.00"),
        )

        with override_settings(TIEMPO_GRACIA_PAGO_SUELTO_MINUTOS=15):
            canceladas = reconciliar_vencimientos_sueltas()

        suelta_con_sena.refresh_from_db()
        self.assertEqual(canceladas, 0)
        self.assertEqual(suelta_con_sena.estado, Inscripcion.Estado.PENDIENTE_PAGO)
