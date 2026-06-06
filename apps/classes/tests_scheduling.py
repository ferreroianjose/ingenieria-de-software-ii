from django.test import TestCase
from django.test.utils import override_settings

from apps.classes.scheduling import ensure_reconciliation_schedule


class ReconciliationSchedulingTests(TestCase):
    def setUp(self):
        from django_q.models import Schedule

        Schedule.objects.filter(
            name="classes.reconciliar_vencimientos_mensuales"
        ).delete()
        Schedule.objects.filter(
            name="classes.reconciliar_vencimientos_sueltas"
        ).delete()

    @override_settings(
        AUTO_RECONCILIACION_MENSUAL_ACTIVA=True,
        AUTO_RECONCILIACION_MENSUAL_HORA="03:45",
    )
    def test_crea_schedule_diario_reconciliacion(self):
        from django_q.models import Schedule

        ensure_reconciliation_schedule()
        schedule = Schedule.objects.get(name="classes.reconciliar_vencimientos_mensuales")

        self.assertEqual(
            schedule.func, "apps.classes.services.reconciliar_vencimientos_mensuales"
        )
        self.assertEqual(schedule.repeats, -1)
        self.assertEqual(schedule.next_run.hour, 3)
        self.assertEqual(schedule.next_run.minute, 45)

    @override_settings(AUTO_RECONCILIACION_MENSUAL_ACTIVA=False)
    def test_no_crea_schedule_si_esta_deshabilitado(self):
        from django_q.models import Schedule

        ensure_reconciliation_schedule()
        self.assertFalse(
            Schedule.objects.filter(
                name="classes.reconciliar_vencimientos_mensuales"
            ).exists()
        )

    @override_settings(
        AUTO_RECONCILIACION_SUELTA_ACTIVA=True,
        FRECUENCIA_RECONCILIACION_SUELTA_MINUTOS=15,
    )
    def test_crea_schedule_minutos_reconciliacion_sueltas(self):
        from django_q.models import Schedule

        ensure_reconciliation_schedule()
        schedule = Schedule.objects.get(name="classes.reconciliar_vencimientos_sueltas")

        self.assertEqual(
            schedule.func, "apps.classes.services.reconciliar_vencimientos_sueltas"
        )
        self.assertEqual(schedule.repeats, -1)
        self.assertEqual(schedule.schedule_type, getattr(Schedule, "MINUTES", "I"))
        self.assertEqual(schedule.minutes, 15)

    @override_settings(AUTO_RECONCILIACION_SUELTA_ACTIVA=False)
    def test_no_crea_schedule_sueltas_si_esta_deshabilitado(self):
        from django_q.models import Schedule

        ensure_reconciliation_schedule()
        self.assertFalse(
            Schedule.objects.filter(
                name="classes.reconciliar_vencimientos_sueltas"
            ).exists()
        )
