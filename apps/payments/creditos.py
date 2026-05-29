"""Consultas de créditos por cancelación anticipada."""

from apps.classes.services import obtener_periodo_activo_si_hay
from apps.payments.models import Credito


def creditos_disponibles_count(usuario, periodo=None):
    if periodo is None:
        periodo = obtener_periodo_activo_si_hay()
    if periodo is None:
        return 0
    return Credito.objects.filter(
        usuario=usuario,
        periodo=periodo,
        estado=Credito.Estado.DISPONIBLE,
    ).count()
