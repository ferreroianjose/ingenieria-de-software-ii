"""Helpers para el flujo cliente: actividades → clase → pago."""

from django.urls import reverse
from django.utils import timezone

from apps.classes.models import Class, Disciplina, Inscripcion
from apps.classes.ocurrencias import fechas_suelta_ocupadas, primera_ocurrencia_activa
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


def mis_inscripciones_activas(clase, usuario):
    """Todas las inscripciones activas del usuario en la clase.

    Devuelve un queryset (excluye CANCELADA) ordenado por fecha de inscripción
    ascendente. Permite tener varias CLASE_SUELTA en distintas fechas, o una
    MENSUAL vigente + otra MENSUAL del próximo período (renovación de abonado).
    """
    if not getattr(usuario, "is_authenticated", False):
        return Inscripcion.objects.none()
    return (
        clase.inscripciones.filter(usuario=usuario)
        .exclude(estado=Inscripcion.Estado.CANCELADA)
        .select_related("periodo")
        .prefetch_related("ocurrencias")
        .order_by("fecha_inscripcion")
    )


def hay_ocurrencia_suelta_libre(clase, usuario):
    ocupadas = fechas_suelta_ocupadas(clase, usuario)
    from apps.classes.services import _normalizar_fecha_clase, ocurrencias_clase_en_ventana

    return any(
        _normalizar_fecha_clase(dt) not in ocupadas
        for dt, _ in ocurrencias_clase_en_ventana(clase)
    )


def periodos_inscripcion_para_clase(clase, usuario=None):
    """Opciones para el formulario de detalle (fechas sueltas + períodos mensuales).

    Si se pasa `usuario`, la lista MENSUAL solo incluye el próximo período
    cuando el usuario es abonado y la `clase` está entre sus renovables
    (ver `apps.payments.periodos.clases_renovables_abonado`).
    """
    from apps.payments.periodos import (
        clases_renovables_abonado,
        hint_periodo_mensual,
        periodo_vigente,
        periodos_elegibles_clase_suelta,
        periodos_elegibles_mensual,
    )

    periodos_suelta_elegibles = {
        p.id for p in periodos_elegibles_clase_suelta()
    }
    suelta = []
    for dt, periodo in ocurrencias_clase_en_ventana(clase):
        if periodo.id not in periodos_suelta_elegibles:
            continue
        cupo_dt = cupo_disponible(clase, fecha=dt, periodo=periodo)
        suelta.append(
            {
                "fecha_clase": dt.isoformat(),
                "fecha_dt": dt,
                "periodo_id": periodo.id,
                "periodo_nombre": periodo.nombre,
                "cupo": cupo_dt,
            }
        )

    from apps.classes.services import clases_mensuales_cobrables

    vigente = periodo_vigente()
    renovables = (
        clases_renovables_abonado(usuario)
        if usuario is not None
        else set()
    )
    mensual = []
    for p in periodos_elegibles_mensual(usuario=usuario):
        if clases_mensuales_cobrables(clase, p) <= 0:
            continue
        # El próximo período solo aparece si la clase es renovable por el usuario.
        es_siguiente = vigente is not None and p.id != vigente.id
        if es_siguiente and clase.id not in renovables:
            continue
        mensual.append(
            {
                "id": p.id,
                "nombre": p.nombre,
                "etiqueta": p.nombre,
                "hint": hint_periodo_mensual(p),
                "cupo": cupo_disponible(clase, periodo=p),
            }
        )

    return {"CLASE_SUELTA": suelta, "MENSUAL": mensual}


def _estado_ui_para_inscripcion(inscripcion, request=None):
    """Estado UI de UNA inscripción, considerando si hay intento de pago activo.

    Devuelve uno de: 'reservada', 'en_espera', 'pendiente_pago', 'en_pago'.
    """
    from apps.payments.inscripcion_pago import (
        inscripcion_tiene_intento_pago,
        intencion_pago_para_clase,
    )

    if inscripcion.estado == Inscripcion.Estado.ESPERA:
        return "en_espera"
    if inscripcion.estado == Inscripcion.Estado.RESERVADA:
        return "reservada"
    if inscripcion.estado == Inscripcion.Estado.PENDIENTE_PAGO:
        if inscripcion_tiene_intento_pago(inscripcion):
            return "pendiente_pago"
        # Hay sesión de intención abierta apuntando a esta clase
        if request and intencion_pago_para_clase(request, inscripcion.clase_id):
            return "en_pago"
        return "pendiente_pago"
    return "reservada"


def _accion_para_item(inscripcion, estado_ui):
    """Acción primaria + secundaria sugeridas para esta inscripción.

    Devuelve dict con `primaria` y `secundaria` (puede ser None). Cada acción
    es a su vez un dict consumible por el template.
    """
    from apps.classes.confirmaciones import (
        acciones_anular_inscripcion_impaga,
        mensaje_confirm_cancelar_reserva_suelta,
        mensaje_confirm_salir_lista_espera,
    )

    if estado_ui == "en_espera":
        return {
            "primaria": {
                "kind": "abandonar_espera",
                "url": reverse("classes:abandonar_espera", args=[inscripcion.id]),
                "label": "Abandonar lista de espera",
                "method": "post",
                "variant": "danger",
                "confirm_message": mensaje_confirm_salir_lista_espera(inscripcion),
                "confirm_title": "Salir de lista de espera",
                "confirm_label": "Sí, salir",
                "confirm_cancel_label": "No, volver",
            },
            "secundaria": None,
        }

    if estado_ui in ("pendiente_pago", "en_pago"):
        anular = acciones_anular_inscripcion_impaga(inscripcion)
        return {
            "primaria": {
                "kind": "ir_a_pagar",
                "url": reverse("payments:seleccion_pago", args=[inscripcion.id]),
                "label": (
                    "Continuar al pago"
                    if estado_ui == "en_pago"
                    else "Ir a pagar"
                ),
                "method": "get",
            },
            "secundaria": {
                "kind": "anular_inscripcion",
                "url": reverse("classes:cancelar_reserva", args=[inscripcion.id]),
                "label": anular["label"],
                "method": "post",
                "variant": "danger",
                "confirm_title": anular["confirm_title"],
                "confirm_message": anular["confirm_message"],
                "confirm_label": anular["confirm_label"],
                "confirm_cancel_label": "No, volver",
            },
        }

    # estado_ui == "reservada"
    if inscripcion.tipo == Inscripcion.Tipo.MENSUAL:
        return {
            "primaria": {
                "kind": "gestionar_mensual",
                "url": reverse("classes:mis_reservas"),
                "label": "Gestionar clases del mes",
                "method": "get",
            },
            "secundaria": None,
        }

    # SUELTA RESERVADA → cancelar la reserva puntual.
    return {
        "primaria": {
            "kind": "cancelar_reserva_suelta",
            "url": reverse("classes:cancelar_reserva", args=[inscripcion.id]),
            "label": "Cancelar reserva",
            "method": "post",
            "variant": "danger",
            "confirm_title": "Cancelar reserva",
            "confirm_message": mensaje_confirm_cancelar_reserva_suelta(inscripcion),
            "confirm_label": "Sí, cancelar",
            "confirm_cancel_label": "No, volver",
        },
        "secundaria": None,
    }


_ESTADO_BADGE = {
    "reservada": {"level": "success", "label": "Reservada"},
    "en_espera": {"level": "warning", "label": "En lista de espera"},
    "pendiente_pago": {"level": "warning-alert", "label": "Pendiente de pago"},
    "en_pago": {"level": "warning-alert", "label": "Pago iniciado"},
}


_ESTADO_MENSAJE = {
    "en_espera": (
        "Estás en la lista de espera para este horario. "
        "Si se libera un cupo te avisamos para que completes el pago."
    ),
    "pendiente_pago": (
        "Tenés una inscripción pendiente de pago. "
        "Completá el pago para confirmar el cupo."
    ),
    "en_pago": (
        "Tenés una reserva iniciada. "
        "Completá el pago para confirmar el cupo."
    ),
}


def _etiqueta_para_inscripcion(inscripcion):
    """Texto principal del item: fecha (SUELTA) o nombre del período (MENSUAL)."""
    if inscripcion.tipo == Inscripcion.Tipo.MENSUAL:
        return inscripcion.periodo.nombre if inscripcion.periodo else "Mensualidad"
    fecha = primera_ocurrencia_activa(inscripcion)
    if not fecha:
        return "Clase suelta"
    local = timezone.localtime(fecha)
    return local.strftime("%A %d/%m · %H:%M hs").capitalize()


def info_clase_para_usuario(clase, usuario, request=None):
    """Contexto del detalle de clase para el cliente.

    Devuelve:
    - `inscripciones_activas`: lista por inscripción del usuario en la clase,
      con estado_ui, badge, mensaje opcional y acciones.
    - `periodos_inscripcion`: opciones para inscribirse a NUEVAS fechas/períodos,
      ya filtradas (excluye lo que el usuario tiene activo).
    - `puede_agregar_reserva`: bool.
    - `puede_anotarse_espera`: bool (form muestra "Anotarme en espera" si no hay cupo).
    - `clase`, `proximo_inicio`, `subtitulo`, `tiene_proximo_inicio`: igual que antes.
    """
    inscripciones = list(mis_inscripciones_activas(clase, usuario))

    items = []
    tiene_mensual_activo = False
    for ins in inscripciones:
        estado_ui = _estado_ui_para_inscripcion(ins, request=request)
        item = {
            "inscripcion": ins,
            "tipo": ins.tipo,
            "periodo": ins.periodo if ins.tipo == Inscripcion.Tipo.MENSUAL else None,
            "fecha_dt": (
                primera_ocurrencia_activa(ins)
                if ins.tipo == Inscripcion.Tipo.CLASE_SUELTA
                else None
            ),
            "etiqueta_principal": _etiqueta_para_inscripcion(ins),
            "estado_ui": estado_ui,
            "estado_badge": _ESTADO_BADGE.get(
                estado_ui, {"level": "info", "label": estado_ui}
            ),
            "mensaje": _ESTADO_MENSAJE.get(estado_ui),
            "acciones": _accion_para_item(ins, estado_ui),
        }
        items.append(item)
        if ins.tipo == Inscripcion.Tipo.MENSUAL and estado_ui in (
            "reservada",
            "pendiente_pago",
            "en_pago",
        ):
            tiene_mensual_activo = True

    # Ordeno los items: primero los que requieren atención (pago/espera), después los confirmados.
    orden_estado = {
        "en_pago": 0,
        "pendiente_pago": 1,
        "en_espera": 2,
        "reservada": 3,
    }
    items.sort(
        key=lambda it: (
            orden_estado.get(it["estado_ui"], 99),
            it["fecha_dt"] or timezone.localtime(timezone.now()),
        )
    )

    cupo = cupo_disponible(clase)
    periodos_inscripcion = periodos_inscripcion_para_clase(clase, usuario=usuario)

    # Filtrar fechas que el usuario ya tiene reservadas / en espera / pendientes.
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

    # Si ya tiene una mensual activa, sacamos el período correspondiente del form
    # (no permitimos doble inscripción al mismo mes). El próximo período (renovación
    # del abonado) sigue apareciendo si todavía no se inscribió a él.
    periodos_mensual_ocupados = {
        ins.periodo_id
        for ins in inscripciones
        if ins.tipo == Inscripcion.Tipo.MENSUAL
        and ins.estado != Inscripcion.Estado.CANCELADA
    }
    periodos_inscripcion["MENSUAL"] = [
        p
        for p in periodos_inscripcion["MENSUAL"]
        if p["id"] not in periodos_mensual_ocupados
    ]

    puede_suelta = len(periodos_inscripcion["CLASE_SUELTA"]) > 0
    puede_mensual = len(periodos_inscripcion["MENSUAL"]) > 0
    hay_opciones = puede_suelta or puede_mensual

    inicio = (
        # Si hay reserva confirmada, mostrar su próxima ocurrencia activa;
        # si no, la próxima ocurrencia de la clase.
        next(
            (it["fecha_dt"] for it in items if it["fecha_dt"]),
            None,
        )
        or proxima_ocurrencia(clase)
    )
    subtitulo = (
        f"{clase.get_dia_semana_display()} · horario a confirmar"
        if not inicio
        else ""
    )

    return {
        "clase": clase,
        "proximo_inicio": inicio,
        "subtitulo": subtitulo,
        "tiene_proximo_inicio": bool(inicio),
        "inscripciones_activas": items,
        "tiene_inscripciones_activas": bool(items),
        "periodos_inscripcion": periodos_inscripcion,
        "puede_agregar_reserva": hay_opciones and cupo > 0,
        "puede_anotarse_espera": hay_opciones and cupo == 0,
        "cupo": cupo,
    }
