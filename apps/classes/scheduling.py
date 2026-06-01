from datetime import timedelta

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone


def _hora_reconciliacion_desde_settings():
    raw = getattr(settings, "AUTO_RECONCILIACION_MENSUAL_HORA", "00:15")
    try:
        hour_str, minute_str = raw.split(":")
        hour = int(hour_str)
        minute = int(minute_str)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError
        return hour, minute
    except (ValueError, TypeError):
        return 0, 15


def ensure_reconciliation_schedule(sender=None, **kwargs):
    """
    Crea/actualiza un Schedule diario en Django Q para reconciliar impagos mensuales.
    Se invoca en post_migrate para asegurar idempotencia.
    """
    if not getattr(settings, "AUTO_RECONCILIACION_MENSUAL_ACTIVA", True):
        return

    try:
        from django_q.models import Schedule

        hour, minute = _hora_reconciliacion_desde_settings()
        ahora = timezone.localtime(timezone.now())
        next_run = ahora.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= ahora:
            next_run += timedelta(days=1)

        schedule_type = getattr(Schedule, "DAILY", "D")
        Schedule.objects.update_or_create(
            name="classes.reconciliar_vencimientos_mensuales",
            defaults={
                "func": "apps.classes.services.reconciliar_vencimientos_mensuales",
                "schedule_type": schedule_type,
                "repeats": -1,
                "next_run": next_run,
            },
        )
    except (OperationalError, ProgrammingError):
        # Durante etapas tempranas de migración la tabla de Schedule puede no existir.
        return
