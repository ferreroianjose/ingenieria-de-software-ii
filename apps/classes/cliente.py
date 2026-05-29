"""Helpers para el flujo cliente: actividades → clase → pago."""

from apps.classes.models import Class, Disciplina, Inscripcion
from apps.classes.services import cupo_disponible, ocurrencias_clase_en_ventana, proxima_ocurrencia


def clases_disponibles_qs():
    return (
        Class.objects.filter(estado="disponible")
        .select_related("profesor", "disciplina", "sala", "sala__sede")
        .prefetch_related("inscripciones")
    )


def disciplinas_con_clases():
    ids = (
        clases_disponibles_qs()
        .values_list("disciplina_id", flat=True)
        .distinct()
    )
    return Disciplina.objects.filter(pk__in=ids).order_by("nombre")


def mi_inscripcion_activa(clase, usuario):
    """Inscripción activa más reciente (abono mensual o última suelta)."""
    return (
        clase.inscripciones.filter(usuario=usuario)
        .exclude(estado=Inscripcion.Estado.CANCELADA)
        .order_by("-fecha_inscripcion")
        .first()
    )


def fechas_suelta_ocupadas(clase, usuario):
    from apps.classes.services import _normalizar_fecha_clase

    qs = clase.inscripciones.filter(
        usuario=usuario,
        tipo=Inscripcion.Tipo.CLASE_SUELTA,
        fecha_clase__isnull=False,
    ).exclude(estado=Inscripcion.Estado.CANCELADA)
    return {_normalizar_fecha_clase(i.fecha_clase) for i in qs}


def hay_ocurrencia_suelta_libre(clase, usuario):
    ocupadas = fechas_suelta_ocupadas(clase, usuario)
    from apps.classes.services import _normalizar_fecha_clase, ocurrencias_clase_en_ventana

    return any(
        _normalizar_fecha_clase(dt) not in ocupadas
        for dt, _ in ocurrencias_clase_en_ventana(clase)
    )


def periodos_inscripcion_para_clase(clase):
    """Opciones para el formulario de detalle (fechas sueltas + períodos mensuales)."""
    from apps.payments.periodos import (
        hint_periodo_mensual,
        periodos_elegibles_mensual,
    )

    suelta = []
    for dt, periodo in ocurrencias_clase_en_ventana(clase):
        suelta.append(
            {
                "fecha_clase": dt.isoformat(),
                "fecha_dt": dt,
                "periodo_id": periodo.id,
                "periodo_nombre": periodo.nombre,
            }
        )

    from apps.classes.services import clases_mensuales_cobrables

    mensual = [
        {
            "id": p.id,
            "nombre": p.nombre,
            "etiqueta": p.nombre,
            "hint": hint_periodo_mensual(p),
        }
        for p in periodos_elegibles_mensual()
        if clases_mensuales_cobrables(clase, p) > 0
    ]

    return {"CLASE_SUELTA": suelta, "MENSUAL": mensual}


def info_clase_para_usuario(clase, usuario, request=None):
    from apps.payments.inscripcion_pago import (
        inscripcion_tiene_intento_pago,
        intencion_pago_para_clase,
    )

    mi = mi_inscripcion_activa(clase, usuario)
    cupo = cupo_disponible(clase)
    en_pago = bool(request and intencion_pago_para_clase(request, clase.id))
    tiene_mensual_activo = (
        mi is not None
        and mi.tipo == Inscripcion.Tipo.MENSUAL
        and mi.estado != Inscripcion.Estado.CANCELADA
    )

    if mi is None and en_pago:
        ui_estado = "en_pago"
    elif mi is None:
        ui_estado = "sin_inscripcion"
    elif mi.estado == Inscripcion.Estado.ESPERA:
        ui_estado = "en_espera"
    elif mi.estado == Inscripcion.Estado.RESERVADA:
        if mi.tipo == Inscripcion.Tipo.MENSUAL or not hay_ocurrencia_suelta_libre(
            clase, usuario
        ):
            ui_estado = "inscripto"
        else:
            ui_estado = "sin_inscripcion"
    elif (
        mi.estado == Inscripcion.Estado.PENDIENTE_PAGO
        and inscripcion_tiene_intento_pago(mi)
    ):
        ui_estado = "pendiente_pago"
    elif (
        mi.estado == Inscripcion.Estado.PENDIENTE_PAGO
        and mi.tipo == Inscripcion.Tipo.CLASE_SUELTA
        and hay_ocurrencia_suelta_libre(clase, usuario)
    ):
        ui_estado = "sin_inscripcion"
    else:
        ui_estado = "sin_inscripcion"

    inicio = mi.fecha_clase if mi and mi.fecha_clase else proxima_ocurrencia(clase)
    subtitulo = (
        f"{clase.get_dia_semana_display()} · horario a confirmar"
        if not inicio
        else ""
    )

    periodos_inscripcion = periodos_inscripcion_para_clase(clase)
    ocupadas = fechas_suelta_ocupadas(clase, usuario)
    from django.utils.dateparse import parse_datetime
    from django.utils import timezone as tz

    from apps.classes.services import _normalizar_fecha_clase

    def _parse_iso(iso):
        dt = parse_datetime(iso)
        if dt and tz.is_naive(dt):
            dt = tz.make_aware(dt, tz.get_current_timezone())
        return _normalizar_fecha_clase(dt) if dt else None

    periodos_inscripcion["CLASE_SUELTA"] = [
        o
        for o in periodos_inscripcion["CLASE_SUELTA"]
        if _parse_iso(o["fecha_clase"]) not in ocupadas
    ]

    puede_suelta = len(periodos_inscripcion["CLASE_SUELTA"]) > 0
    puede_mensual = (
        len(periodos_inscripcion["MENSUAL"]) > 0 and not tiene_mensual_activo
    )
    puede_inscribirse = (
        ui_estado == "sin_inscripcion"
        and cupo > 0
        and not en_pago
        and (puede_suelta or puede_mensual)
    )

    return {
        "clase": clase,
        "proximo_inicio": inicio,
        "subtitulo": subtitulo,
        "tiene_proximo_inicio": bool(inicio),
        "mi_inscripcion": mi,
        "ui_estado": ui_estado,
        "periodos_inscripcion": periodos_inscripcion,
        "puede_inscribirse": puede_inscribirse,
        "puede_anotarse_espera": ui_estado == "sin_inscripcion" and cupo == 0,
        "puede_cancelar": ui_estado in ("inscripto", "pendiente_pago"),
        "puede_abandonar_espera": ui_estado == "en_espera",
    }
