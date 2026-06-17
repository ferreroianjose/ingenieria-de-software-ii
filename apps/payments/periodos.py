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


def lunes_semana_iso(fecha=None):
    """Lunes de la semana ISO que contiene `fecha` (default: hoy)."""
    hoy = fecha or timezone.localdate()
    return hoy - timedelta(days=hoy.weekday())


def domingo_semana_iso(fecha=None):
    """Domingo (inclusive) de la semana ISO que contiene `fecha`."""
    return lunes_semana_iso(fecha) + timedelta(days=6)


def es_abonado(usuario, fecha=None):
    """True si el usuario tiene una MENSUAL activa en el período vigente.

    Activa = estado en {RESERVADA, PENDIENTE_PAGO}. Es el "beneficio del abonado":
    haber pagado (o tener reserva con seña) le da derecho a la pre-inscripción
    de renovación del próximo mes.
    """
    if not getattr(usuario, "is_authenticated", False):
        return False
    hoy = fecha or timezone.localdate()
    vigente = periodo_vigente(hoy)
    if not vigente:
        return False
    return Inscripcion.objects.filter(
        usuario=usuario,
        tipo=Inscripcion.Tipo.MENSUAL,
        periodo=vigente,
        estado__in=[
            Inscripcion.Estado.RESERVADA,
            Inscripcion.Estado.PENDIENTE_PAGO,
        ],
    ).exists()


def clases_renovables_abonado(usuario, fecha=None):
    """IDs de clases que el usuario abonado puede renovar al período siguiente.

    Son las clases en las que tiene una MENSUAL activa en el período vigente.
    """
    if not getattr(usuario, "is_authenticated", False):
        return set()
    hoy = fecha or timezone.localdate()
    vigente = periodo_vigente(hoy)
    if not vigente:
        return set()
    return set(
        Inscripcion.objects.filter(
            usuario=usuario,
            tipo=Inscripcion.Tipo.MENSUAL,
            periodo=vigente,
            estado__in=[
                Inscripcion.Estado.RESERVADA,
                Inscripcion.Estado.PENDIENTE_PAGO,
            ],
        ).values_list("clase_id", flat=True)
    )


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


def periodos_elegibles_mensual(fecha=None, usuario=None):
    """
    Períodos elegibles para inscripción mensual.

    - Período en curso: siempre incluido (cualquier usuario).
    - Período siguiente: solo si el usuario es abonado y estamos en la ventana
      de pre-inscripción de abonados. La pre-inscripción es una "renovación":
      el filtro por clase específica ocurre en el caller (ver
      `apps.classes.cliente.periodos_inscripcion_para_clase`).
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

    if (
        siguiente
        and siguiente.id not in vistos
        and en_ventana_preinscripcion_abonados(siguiente, hoy)
        and usuario is not None
        and es_abonado(usuario, hoy)
    ):
        elegibles.append(siguiente)
        vistos.add(siguiente.id)

    return elegibles


def horizonte_clase_suelta(fecha=None):
    """Última fecha (inclusive) elegible para reservar clase suelta.

    Default: domingo de la semana ISO en curso. Si está seteado el override
    `VENTANA_OCURRENCIAS_CLASE_SUELTA_DIAS` (> 0), se respeta como horizonte
    en días.
    """
    hoy = fecha or timezone.localdate()
    override = getattr(settings, "VENTANA_OCURRENCIAS_CLASE_SUELTA_DIAS", 0) or 0
    if override > 0:
        return hoy + timedelta(days=override)
    return domingo_semana_iso(hoy)


def periodos_elegibles_clase_suelta(fecha=None):
    """Períodos que solapan la ventana de reserva (semana ISO por default).

    Aplica a todos los usuarios (abonados o no). La ventana es semanal:
    el lunes ven 7 días, el sábado solo 1.
    """
    hoy = fecha or timezone.localdate()
    hasta = horizonte_clase_suelta(hoy)
    periodos = PeriodoCobro.objects.filter(
            fecha_inicio_periodo__lte=hasta,
            fecha_fin_periodo__gte=hoy,
        ).order_by("fecha_inicio_periodo")
    return [p for p in periodos if periodo_habilitado_clase_suelta(p, hoy)]


def periodos_elegibles_para(tipo, fecha=None, usuario=None):
    if tipo == Inscripcion.Tipo.MENSUAL:
        return periodos_elegibles_mensual(fecha, usuario=usuario)
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
