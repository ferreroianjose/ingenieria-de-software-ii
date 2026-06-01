"""Reglas de qué períodos de cobro admite cada modalidad de inscripción."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.classes.models import Inscripcion
from apps.payments.models import PeriodoCobro

def dias_preinscripcion_abonados():
    return getattr(settings, "DIAS_PREINSCRIPCION_ABONADOS", 10)


def habilitar_precola_no_abonados():
    return getattr(settings, "HABILITAR_PRECOLA_NO_ABONADOS", True)


def dia_limite_pago_mensual():
    return getattr(settings, "DIA_LIMITE_PAGO_MENSUAL", 10)


def periodo_conteniendo_fecha(fecha):
    """Período de cobro cuyo rango incluye la fecha (día calendario)."""
    return (
        PeriodoCobro.objects.filter(
            fecha_inicio_periodo__lte=fecha,
            fecha_fin_periodo__gte=fecha,
        )
        .order_by("-fecha_inicio_periodo")
        .first()
    )


def periodo_vigente(fecha=None):
    hoy = fecha or timezone.localdate()
    return (
        PeriodoCobro.objects.filter(
            fecha_inicio_periodo__lte=hoy,
            fecha_fin_periodo__gte=hoy,
        )
        .order_by("-fecha_inicio_periodo")
        .first()
    )


def periodo_siguiente(periodo, fecha=None):
    if periodo is None:
        return None
    hoy = fecha or timezone.localdate()
    return (
        PeriodoCobro.objects.filter(fecha_inicio_periodo__gt=periodo.fecha_fin_periodo)
        .filter(fecha_inicio_periodo__gte=hoy)
        .order_by("fecha_inicio_periodo")
        .first()
    )


def en_ventana_preinscripcion_abonados(periodo, fecha=None):
    """Desde apertura_abonados (o N días antes del inicio) hasta el día anterior al inicio."""
    hoy = fecha or timezone.localdate()
    if hoy >= periodo.fecha_inicio_periodo:
        return False
    limite = periodo.fecha_inicio_periodo - timedelta(days=dias_preinscripcion_abonados())
    return hoy >= max(periodo.apertura_abonados, limite)


def vencimiento_mensual_alcanzado(periodo, fecha=None):
    """True cuando venció el plazo de pago mensual del período (después del día límite)."""
    hoy = fecha or timezone.localdate()
    if not (
        periodo.fecha_inicio_periodo <= hoy <= periodo.fecha_fin_periodo
    ):
        return False
    return hoy.day > dia_limite_pago_mensual()


def periodo_habilitado_clase_suelta(periodo, fecha=None):
    """
    Un período de clase suelta se considera habilitado si:
    - abrió inscripción general, o
    - aún no abrió general pero está habilitada la pre-cola y hay ventana de abonados.
    """
    hoy = fecha or timezone.localdate()
    if hoy >= periodo.apertura_general:
        return True
    if not habilitar_precola_no_abonados():
        return False
    return en_ventana_preinscripcion_abonados(periodo, hoy)


def requiere_precola_suelta(periodo, fecha=None):
    """True si no abonado puede anotarse, pero solo en espera (antes de apertura general)."""
    hoy = fecha or timezone.localdate()
    return periodo_habilitado_clase_suelta(periodo, hoy) and hoy < periodo.apertura_general


def periodos_elegibles_mensual(fecha=None):
    """
    Abono: período en curso o preinscripción al siguiente (no solo el vigente).
    """
    hoy = fecha or timezone.localdate()
    elegibles = []
    vistos = set()

    vigente = periodo_vigente(hoy)
    if vigente and vigente.id not in vistos:
        elegibles.append(vigente)
        vistos.add(vigente.id)

    if vigente:
        siguiente = periodo_siguiente(vigente, hoy)
    else:
        siguiente = (
            PeriodoCobro.objects.filter(fecha_inicio_periodo__gt=hoy)
            .order_by("fecha_inicio_periodo")
            .first()
        )

    if siguiente and siguiente.id not in vistos and en_ventana_preinscripcion_abonados(
        siguiente, hoy
    ):
        elegibles.append(siguiente)
        vistos.add(siguiente.id)

    return elegibles


def periodos_elegibles_clase_suelta(fecha=None):
    """Períodos que solapan la ventana de reserva de clase suelta (~3 semanas)."""
    hoy = fecha or timezone.localdate()
    dias = getattr(settings, "VENTANA_OCURRENCIAS_CLASE_SUELTA_DIAS", 21)
    hasta = hoy + timedelta(days=dias)
    periodos = PeriodoCobro.objects.filter(
            fecha_inicio_periodo__lte=hasta,
            fecha_fin_periodo__gte=hoy,
        ).order_by("fecha_inicio_periodo")
    return [p for p in periodos if periodo_habilitado_clase_suelta(p, hoy)]


def periodos_elegibles_para(tipo, fecha=None):
    if tipo == Inscripcion.Tipo.MENSUAL:
        return periodos_elegibles_mensual(fecha)
    return periodos_elegibles_clase_suelta(fecha)


def etiqueta_periodo_inscripcion(periodo, tipo, fecha=None):
    """Nombre del período para pantallas del cliente (sin jerga interna)."""
    return periodo.nombre


def hint_periodo_mensual(periodo, fecha=None):
    """Texto aclaratorio bajo cada opción de mes."""
    hoy = fecha or timezone.localdate()
    if periodo.fecha_inicio_periodo > hoy:
        return (
            f"Todas las clases de este horario desde el "
            f"{periodo.fecha_inicio_periodo:%d/%m}"
        )
    if periodo.fecha_inicio_periodo <= hoy <= periodo.fecha_fin_periodo:
        return "Todas las clases de este horario que queden en el mes"
    return "Todas las clases de este horario en el período"
