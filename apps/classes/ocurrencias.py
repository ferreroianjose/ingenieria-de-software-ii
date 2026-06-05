"""Sesiones concretas (fecha/hora) vinculadas a una inscripción."""

from django.conf import settings
from django.utils import timezone

from apps.classes.models import Inscripcion, InscripcionOcurrencia


def _horas_minimas_credito_mensual():
    return getattr(settings, "CANCELACION_MENSUAL_HORAS_MIN", 48)


def _mensaje_ocurrencia_cancelada(oc):
    if oc.otorga_credito and oc.credito_id:
        return "Cancelada · crédito otorgado"
    return "Cancelada · sesión perdida"


def _mensaje_ocurrencia_activa(inscripcion):
    if inscripcion.tipo == Inscripcion.Tipo.MENSUAL:
        return "Incluida en mensualidad"
    return "Clase individual"


def _confirm_cancelacion_mensual(inscripcion, fecha_clase, horas_restantes):
    from apps.classes.confirmaciones import mensaje_confirm_cancelar_ocurrencia_mensual

    return mensaje_confirm_cancelar_ocurrencia_mensual(
        inscripcion, fecha_clase, horas_restantes
    )


def _normalizar(dt):
    from apps.classes.services import _normalizar_fecha_clase

    return _normalizar_fecha_clase(dt)


def crear_ocurrencia_suelta(inscripcion, fecha_clase):
    return InscripcionOcurrencia.objects.create(
        inscripcion=inscripcion,
        fecha_clase=_normalizar(fecha_clase),
        estado=InscripcionOcurrencia.Estado.ACTIVA,
    )


def generar_ocurrencias_mensual(inscripcion):
    """Idempotente: crea filas ACTIVA para cada sesión del abono confirmado."""
    from apps.classes.services import (
        desde_fecha_cobro_mensual,
        ocurrencias_detalle_en_periodo,
    )

    if inscripcion.tipo != Inscripcion.Tipo.MENSUAL:
        return []
    if inscripcion.ocurrencias.exists():
        return list(inscripcion.ocurrencias.order_by("fecha_clase"))

    desde = desde_fecha_cobro_mensual(inscripcion.periodo)
    fechas = ocurrencias_detalle_en_periodo(
        inscripcion.clase, inscripcion.periodo, desde_fecha=desde
    )
    return InscripcionOcurrencia.objects.bulk_create(
        [
            InscripcionOcurrencia(
                inscripcion=inscripcion,
                fecha_clase=fecha,
                estado=InscripcionOcurrencia.Estado.ACTIVA,
            )
            for fecha in fechas
        ]
    )


def fecha_suelta_reservada(usuario, clase, fecha_clase):
    """True si el usuario ya tiene esa fecha suelta reservada (inscripción activa)."""
    normalizada = _normalizar(fecha_clase)
    return InscripcionOcurrencia.objects.filter(
        inscripcion__usuario=usuario,
        inscripcion__clase=clase,
        inscripcion__tipo=Inscripcion.Tipo.CLASE_SUELTA,
        inscripcion__estado__in=(
            Inscripcion.Estado.RESERVADA,
            Inscripcion.Estado.PENDIENTE_PAGO,
            Inscripcion.Estado.ESPERA,
        ),
        fecha_clase=normalizada,
        estado=InscripcionOcurrencia.Estado.ACTIVA,
    ).exists()


def fechas_suelta_ocupadas(clase, usuario):
    qs = InscripcionOcurrencia.objects.filter(
        inscripcion__clase=clase,
        inscripcion__usuario=usuario,
        inscripcion__tipo=Inscripcion.Tipo.CLASE_SUELTA,
        inscripcion__estado__in=(
            Inscripcion.Estado.RESERVADA,
            Inscripcion.Estado.PENDIENTE_PAGO,
            Inscripcion.Estado.ESPERA,
        ),
        estado=InscripcionOcurrencia.Estado.ACTIVA,
    )
    return {_normalizar(o.fecha_clase) for o in qs}


def primera_ocurrencia_activa(inscripcion):
    oc = (
        inscripcion.ocurrencias.filter(
            estado=InscripcionOcurrencia.Estado.ACTIVA,
            fecha_clase__gt=timezone.now(),
        )
        .order_by("fecha_clase")
        .first()
    )
    return oc.fecha_clase if oc else None


def marcar_ocurrencias_inscripcion_canceladas(inscripcion):
    inscripcion.ocurrencias.filter(estado=InscripcionOcurrencia.Estado.ACTIVA).update(
        estado=InscripcionOcurrencia.Estado.CANCELADA
    )


def _filas_desde_queryset(ocurrencias_qs):
    from apps.payments.cancelaciones import horas_hasta_clase

    ahora = timezone.localtime(timezone.now())
    filas = []
    for oc in ocurrencias_qs:
        dt = oc.fecha_clase
        cancelada = oc.estado == InscripcionOcurrencia.Estado.CANCELADA
        horas_restantes = horas_hasta_clase(dt) if dt > ahora else None
        inscripcion = oc.inscripcion
        puede_cancelar = not cancelada and dt > ahora and (
            (
                inscripcion.tipo == Inscripcion.Tipo.MENSUAL
                and inscripcion.estado == Inscripcion.Estado.RESERVADA
            )
            or (
                inscripcion.tipo == Inscripcion.Tipo.CLASE_SUELTA
                and inscripcion.estado == Inscripcion.Estado.RESERVADA
            )
        )
        filas.append(
            {
                "fecha": dt,
                "ocurrencia_id": oc.id,
                "cancelada": cancelada,
                "otorga_credito": cancelada and oc.otorga_credito and oc.credito_id,
                "mensaje_estado": (
                    _mensaje_ocurrencia_cancelada(oc)
                    if cancelada
                    else _mensaje_ocurrencia_activa(oc.inscripcion)
                ),
                "confirm_cancelacion": (
                    _confirm_cancelacion_mensual(
                        oc.inscripcion, dt, horas_restantes
                    )
                    if puede_cancelar
                    else None
                ),
                "puede_cancelar": puede_cancelar,
                "horas_restantes": horas_restantes,
            }
        )
    return filas


def _filas_desde_calendario(inscripcion, desde_fecha=None):
    """Vista previa cuando aún no hay filas persistidas (p. ej. mensual pendiente de pago)."""
    from apps.classes.services import ocurrencias_detalle_en_periodo
    from apps.payments.cancelaciones import horas_hasta_clase

    todas = ocurrencias_detalle_en_periodo(
        inscripcion.clase, inscripcion.periodo, desde_fecha=desde_fecha
    )
    ahora = timezone.localtime(timezone.now())
    return [
        {
            "fecha": dt,
            "ocurrencia_id": None,
            "cancelada": False,
            "otorga_credito": False,
            "mensaje_estado": _mensaje_ocurrencia_activa(inscripcion),
            "confirm_cancelacion": None,
            "puede_cancelar": False,
            "horas_restantes": horas_hasta_clase(dt) if dt > ahora else None,
        }
        for dt in todas
    ]


def ocurrencias_reserva_ui(inscripcion, desde_fecha=None):
    hoy = desde_fecha or timezone.localdate()
    ahora = timezone.now()

    qs = (
        inscripcion.ocurrencias.filter(fecha_clase__date__gte=hoy)
        .select_related("credito", "inscripcion")
        .order_by("fecha_clase")
    )
    if qs.exists():
        return _filas_desde_queryset(qs)

    if inscripcion.tipo == Inscripcion.Tipo.MENSUAL:
        return _filas_desde_calendario(inscripcion, desde_fecha=hoy)

    from apps.classes.services import proxima_ocurrencia
    from apps.payments.cancelaciones import horas_hasta_clase

    ocurrencia = proxima_ocurrencia(inscripcion.clase)
    if not ocurrencia:
        return []
    horas = horas_hasta_clase(ocurrencia) if ocurrencia > ahora else None
    puede_cancelar = inscripcion.estado == Inscripcion.Estado.RESERVADA
    return [
        {
            "fecha": ocurrencia,
            "ocurrencia_id": None,
            "cancelada": False,
            "otorga_credito": False,
            "mensaje_estado": _mensaje_ocurrencia_activa(inscripcion),
            "confirm_cancelacion": None,
            "puede_cancelar": puede_cancelar,
            "horas_restantes": horas,
        }
    ]


def proximas_ocurrencias_dashboard(usuario, limite=4):
    """Próximas sesiones ACTIVA de inscripciones no canceladas."""
    return (
        InscripcionOcurrencia.objects.filter(
            inscripcion__usuario=usuario,
            inscripcion__estado__in=(
                Inscripcion.Estado.RESERVADA,
                Inscripcion.Estado.PENDIENTE_PAGO,
            ),
            estado=InscripcionOcurrencia.Estado.ACTIVA,
            fecha_clase__gt=timezone.now(),
        )
        .select_related(
            "inscripcion",
            "inscripcion__clase",
            "inscripcion__clase__disciplina",
            "inscripcion__clase__sala",
            "inscripcion__clase__sala__sede",
        )
        .order_by("fecha_clase")[:limite]
    )
