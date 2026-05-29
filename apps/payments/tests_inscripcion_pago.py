from decimal import Decimal
from datetime import date, time, timedelta

from django.test import TestCase

from apps.classes.models import Class, Disciplina, Inscripcion, Sede, Sala, Teacher
from apps.payments.inscripcion_pago import monto_a_cobrar, resumen_pago_inscripcion
from apps.payments.models import Pago, PagoInscripcion, PeriodoCobro, PrecioDisciplina
from django.contrib.auth import get_user_model

User = get_user_model()


class InscripcionPagoHelpersTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="helper@test.com",
            email="helper@test.com",
            password="testpassword123",
            dni="99999999",
        )
        sede = Sede.objects.create(nombre="Sede H", direccion="Calle H")
        sala = Sala.objects.create(nombre="Sala H", capacidad=10, sede=sede)
        teacher = Teacher.objects.create(nombre="Ana", apellido="Lopez")
        self.disciplina = Disciplina.objects.create(nombre="Yoga")
        self.periodo = PeriodoCobro.objects.create(
            nombre="Sep 2026",
            fecha_inicio_periodo=date(2026, 9, 1),
            fecha_fin_periodo=date(2026, 9, 30),
            apertura_abonados=date(2026, 8, 20),
            apertura_general=date(2026, 9, 1),
        )
        self.clase = Class.objects.create(
            disciplina=self.disciplina,
            sala=sala,
            profesor=teacher,
            dia_semana=2,
            duracion=timedelta(hours=1),
            hora_inicio=time(9, 0),
            cupo_maximo=10,
        )
        self.inscripcion = Inscripcion.objects.create(
            usuario=self.user,
            clase=self.clase,
            periodo=self.periodo,
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
            estado=Inscripcion.Estado.PENDIENTE_PAGO,
        )
        PrecioDisciplina.objects.create(
            disciplina=self.disciplina,
            periodo=self.periodo,
            monto=Decimal("4000.00"),
        )

    def test_resumen_muestra_pagar_saldo_tras_sena(self):
        pago = Pago.objects.create(
            usuario=self.user,
            periodo=self.periodo,
            monto=Decimal("2000.00"),
            estado=Pago.Estado.COMPLETADO,
            metodo=Pago.Metodo.MERCADOPAGO,
        )
        PagoInscripcion.objects.create(
            pago=pago, inscripcion=self.inscripcion, monto_aplicado=Decimal("2000.00")
        )

        resumen = resumen_pago_inscripcion(self.inscripcion)

        self.assertTrue(resumen["mostrar_pagar_saldo"])
        self.assertFalse(resumen["mostrar_pagar"])
        self.assertEqual(resumen["saldo_restante"], Decimal("2000.00"))

    def test_monto_a_cobrar_saldo(self):
        pago = Pago.objects.create(
            usuario=self.user,
            periodo=self.periodo,
            monto=Decimal("2000.00"),
            estado=Pago.Estado.COMPLETADO,
            metodo=Pago.Metodo.MERCADOPAGO,
        )
        PagoInscripcion.objects.create(
            pago=pago, inscripcion=self.inscripcion, monto_aplicado=Decimal("2000.00")
        )

        self.assertEqual(monto_a_cobrar(self.inscripcion, "SALDO"), Decimal("2000.00"))
