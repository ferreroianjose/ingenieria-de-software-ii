from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.classes.confirmaciones import (
    acciones_anular_inscripcion_impaga,
    etiqueta_horario_clase,
    mensaje_confirm_anular_inscripcion_impaga,
    mensaje_confirm_cancelar_ocurrencia_mensual,
    mensaje_confirm_cancelar_reserva_suelta,
    mensaje_confirm_salir_lista_espera,
)
from apps.classes.models import Class, Disciplina, Inscripcion, Sala, Sede, Teacher
from apps.classes.ocurrencias import crear_ocurrencia_suelta
from apps.payments.models import PeriodoCobro, PrecioDisciplina

User = get_user_model()


class ConfirmacionesMensajesTest(TestCase):
    def setUp(self):
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
        profesor = Teacher.objects.create(nombre="Carlos", apellido="Sánchez")
        self.clase = Class.objects.create(
            disciplina=self.disciplina,
            sala=sala,
            profesor=profesor,
            dia_semana=0,
            hora_inicio=time(7, 0),
            duracion=timedelta(hours=1),
            cupo_maximo=10,
            estado="disponible",
        )
        self.user = User.objects.create_user(
            username="confirm@test.com",
            email="confirm@test.com",
            password="testpassword123",
            dni="99887766",
            telefono_emergencia="3515550000",
        )

    def test_etiqueta_horario_incluye_disciplina_profesor_y_horario(self):
        etiqueta = etiqueta_horario_clase(self.clase)
        self.assertEqual(
            etiqueta,
            "Yoga - Carlos Sánchez - Lunes 07:00",
        )

    def test_mensaje_cancelar_reserva_menciona_clase(self):
        inscripcion = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.RESERVADA,
        )
        tz = timezone.get_current_timezone()
        fecha = timezone.make_aware(datetime(2026, 5, 22, 7, 0), tz)
        crear_ocurrencia_suelta(inscripcion, fecha)
        msg = mensaje_confirm_cancelar_reserva_suelta(inscripcion)
        self.assertIn("«Yoga - Carlos Sánchez - Lunes 07:00»", msg)

    def test_mensaje_salir_espera_menciona_clase(self):
        inscripcion = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.ESPERA,
        )
        msg = mensaje_confirm_salir_lista_espera(inscripcion)
        self.assertIn("lista de espera", msg)
        self.assertIn("«Yoga - Carlos Sánchez - Lunes 07:00»", msg)

    def test_mensaje_anular_inscripcion_mensual_impaga(self):
        inscripcion = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.MENSUAL,
            estado=Inscripcion.Estado.PENDIENTE_PAGO,
        )
        msg = mensaje_confirm_anular_inscripcion_impaga(inscripcion)
        self.assertIn("inscripción mensual", msg)
        self.assertIn("no hay pagos que reintegrar", msg.lower())

    def test_acciones_anular_inscripcion_impaga_sin_pago(self):
        inscripcion = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.PENDIENTE_PAGO,
        )
        acciones = acciones_anular_inscripcion_impaga(inscripcion)
        self.assertEqual(acciones["label"], "Anular inscripción")

    def test_mensaje_cancelar_ocurrencia_con_credito(self):
        inscripcion = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.MENSUAL,
            estado=Inscripcion.Estado.RESERVADA,
        )
        fecha = timezone.make_aware(datetime(2026, 5, 5, 7, 0), timezone.get_current_timezone())
        msg = mensaje_confirm_cancelar_ocurrencia_mensual(inscripcion, fecha, 72)
        self.assertIn("«Yoga - Carlos Sánchez - Lunes 07:00»", msg)
        self.assertIn("05/05/2026", msg)
        self.assertIn("crédito", msg.lower())
