from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

from apps.payments.models import PeriodoCobro

from .exceptions import (
    CancelacionMensualNoPermitida,
    ClaseNoDisponible,
    ClaseNoEncontrada,
    InscripcionDuplicada,
    InscripcionNoEncontrada,
    InscripcionYaCancelada,
    OcurrenciaNoValida,
    OcurrenciaYaCancelada,
    PeriodoCobroInactivo,
    ReservaError,
    TelefonoEmergenciaFaltante,
)
from .models import Class, Inscripcion, InscripcionOcurrencia

# ── Helpers ───────────────────────────────────────────────────────────────────

def proxima_ocurrencia(clase):
    """Próxima fecha/hora de este horario (sin acotar a un período de cobro)."""
    vigente = obtener_periodo_activo_si_hay()
    if vigente:
        en_periodo = proxima_ocurrencia_en_periodo(clase, vigente)
        if en_periodo:
            return en_periodo
    return _proxima_ocurrencia_desde(clase, timezone.localdate())


def _proxima_ocurrencia_desde(clase, desde_fecha):
    if not clase.hora_inicio:
        return None
    ahora = timezone.localtime(timezone.now())
    tz = timezone.get_current_timezone()
    days_ahead = (clase.dia_semana - desde_fecha.weekday()) % 7
    dt = timezone.make_aware(
        datetime.combine(desde_fecha + timedelta(days=days_ahead), clase.hora_inicio),
        tz,
    )
    if dt <= ahora:
        dt += timedelta(days=7)
    return dt


def ocurrencias_clase_en_ventana(clase, dias=None, desde_fecha=None):
    """
    Ocurrencias futuras del horario dentro de los próximos `dias` (default 21).
    Cada ítem es (datetime aware, PeriodoCobro que contiene esa fecha).
    """
    from django.conf import settings

    from apps.payments.periodos import periodo_conteniendo_fecha

    if not clase.hora_inicio:
        return []

    dias = dias or getattr(settings, "VENTANA_OCURRENCIAS_CLASE_SUELTA_DIAS", 21)
    ahora = timezone.localtime(timezone.now())
    hoy = desde_fecha or ahora.date()
    limite = hoy + timedelta(days=dias)
    tz = timezone.get_current_timezone()
    resultado = []
    cursor = hoy + timedelta(days=(clase.dia_semana - hoy.weekday()) % 7)
    while cursor <= limite:
        dt = timezone.make_aware(datetime.combine(cursor, clase.hora_inicio), tz)
        if dt > ahora:
            periodo = periodo_conteniendo_fecha(cursor)
            if periodo:
                resultado.append((dt, periodo))
        cursor += timedelta(days=7)
    return resultado


def _normalizar_fecha_clase(dt):
    return timezone.localtime(dt).replace(microsecond=0)


def fecha_clase_elegible(clase, fecha_clase):
    """True si la fecha/hora coincide con una ocurrencia en la ventana."""
    if fecha_clase is None:
        return False
    objetivo = _normalizar_fecha_clase(fecha_clase)
    for dt, _ in ocurrencias_clase_en_ventana(clase):
        if _normalizar_fecha_clase(dt) == objetivo:
            return True
    return False


def proxima_ocurrencia_en_periodo(clase, periodo, desde_fecha=None):
    """Primera ocurrencia futura del horario dentro del período de cobro."""
    if not clase.hora_inicio:
        return None
    hoy = desde_fecha or timezone.localdate()
    inicio = max(periodo.fecha_inicio_periodo, hoy)
    if inicio > periodo.fecha_fin_periodo:
        return None
    cursor = inicio + timedelta(days=(clase.dia_semana - inicio.weekday()) % 7)
    ahora = timezone.localtime(timezone.now())
    tz = timezone.get_current_timezone()
    while cursor <= periodo.fecha_fin_periodo:
        dt = timezone.make_aware(datetime.combine(cursor, clase.hora_inicio), tz)
        if dt > ahora:
            return dt
        cursor += timedelta(days=7)
    return None


def ocurrencias_clase_en_periodo(clase, periodo, desde_fecha=None):
    """Cuántas veces se dicta este horario semanal entre desde_fecha y el fin del período."""
    if clase.hora_inicio is None:
        return 0
    hoy = desde_fecha or timezone.localdate()
    inicio = max(periodo.fecha_inicio_periodo, hoy)
    fin = periodo.fecha_fin_periodo
    if inicio > fin:
        return 0
    cursor = inicio + timedelta(days=(clase.dia_semana - inicio.weekday()) % 7)
    total = 0
    while cursor <= fin:
        total += 1
        cursor += timedelta(days=7)
    return total


def ocurrencias_detalle_en_periodo(clase, periodo, desde_fecha=None):
    """Listado de fechas/horas de ocurrencias del horario dentro del período."""
    if clase.hora_inicio is None:
        return []
    hoy = desde_fecha or timezone.localdate()
    inicio = max(periodo.fecha_inicio_periodo, hoy)
    fin = periodo.fecha_fin_periodo
    if inicio > fin:
        return []

    tz = timezone.get_current_timezone()
    cursor = inicio + timedelta(days=(clase.dia_semana - inicio.weekday()) % 7)
    ocurrencias = []
    while cursor <= fin:
        ocurrencias.append(
            timezone.make_aware(datetime.combine(cursor, clase.hora_inicio), tz)
        )
        cursor += timedelta(days=7)
    return ocurrencias


def desde_fecha_cobro_mensual(periodo, fecha=None):
    """Desde qué día se cuentan las clases de un abono mensual."""
    hoy = fecha or timezone.localdate()
    if hoy < periodo.fecha_inicio_periodo:
        return periodo.fecha_inicio_periodo
    return hoy


def clases_mensuales_cobrables(clase, periodo, fecha=None):
    """Ocurrencias futuras del horario dentro del período (base del cobro mensual)."""
    return ocurrencias_clase_en_periodo(
        clase, periodo, desde_fecha=desde_fecha_cobro_mensual(periodo, fecha)
    )


def obtener_periodo_activo_si_hay():
    """Período vigente hoy, o None si no hay ninguno (no lanza excepción)."""
    from apps.payments.periodos import periodo_vigente

    return periodo_vigente()


def obtener_periodo_activo():
    """Período de cobro vigente según la fecha de hoy."""
    periodo = obtener_periodo_activo_si_hay()
    if not periodo:
        raise PeriodoCobroInactivo()
    return periodo


def resolver_periodo_inscripcion(periodo_id, tipo, fecha_clase=None):
    """Valida que el período elegido aplique a la modalidad."""
    from apps.payments.models import PeriodoCobro
    from apps.payments.periodos import periodo_conteniendo_fecha, periodos_elegibles_para

    try:
        periodo = PeriodoCobro.objects.get(pk=periodo_id)
    except PeriodoCobro.DoesNotExist as err:
        raise PeriodoCobroInactivo() from err

    if tipo == Inscripcion.Tipo.CLASE_SUELTA and fecha_clase:
        periodo_fecha = periodo_conteniendo_fecha(
            timezone.localdate(_normalizar_fecha_clase(fecha_clase))
        )
        if not periodo_fecha or periodo_fecha.id != periodo.id:
            raise ReservaError(
                "El período de cobro no coincide con la fecha de la clase."
            )
        return periodo

    elegibles = {p.id: p for p in periodos_elegibles_para(tipo)}
    if periodo.id not in elegibles:
        raise ReservaError(
            "El período seleccionado no está abierto para esta modalidad."
        )
    return periodo


def cupo_disponible(clase):
    """Cupos libres: inscripciones RESERVADA o PENDIENTE_PAGO (creadas al intentar pagar)."""
    activas = clase.inscripciones.filter(
        estado__in=[Inscripcion.Estado.RESERVADA, Inscripcion.Estado.PENDIENTE_PAGO]
    ).count()
    return max(0, clase.cupo_maximo - activas)


def validar_intencion_inscripcion(
    usuario, clase_id, periodo, tipo, fecha_clase=None, permitir_sin_cupo=False
):
    """Comprueba que el usuario puede inscribirse; no escribe en la BD."""
    if not usuario.telefono_emergencia:
        raise TelefonoEmergenciaFaltante()

    try:
        clase = Class.objects.get(id=clase_id)
    except Class.DoesNotExist as err:
        raise ClaseNoEncontrada() from err

    if clase.estado != "disponible":
        raise ClaseNoDisponible()

    if tipo not in Inscripcion.Tipo.values:
        tipo = Inscripcion.Tipo.CLASE_SUELTA

    if tipo == Inscripcion.Tipo.CLASE_SUELTA:
        if not fecha_clase:
            raise ReservaError("Elegí la fecha de la clase para continuar.")
        if not fecha_clase_elegible(clase, fecha_clase):
            raise ReservaError("La fecha elegida no está disponible para inscripción.")
        from apps.payments.periodos import periodo_conteniendo_fecha

        periodo_fecha = periodo_conteniendo_fecha(timezone.localdate(fecha_clase))
        if not periodo_fecha or periodo_fecha.id != periodo.id:
            raise ReservaError("El período de cobro no coincide con la fecha elegida.")
        from apps.payments.periodos import (
            periodo_habilitado_clase_suelta,
            requiere_precola_suelta,
        )

        if not periodo_habilitado_clase_suelta(periodo):
            raise ReservaError(
                "La inscripción para esa fecha todavía no está habilitada."
            )
        if requiere_precola_suelta(periodo) and not permitir_sin_cupo:
            raise ReservaError(
                "La reserva para no abonados abre el primer día del período. "
                "Por ahora podés anotarte en lista de espera."
            )
        from apps.classes.ocurrencias import fecha_suelta_reservada

        if fecha_suelta_reservada(usuario, clase, fecha_clase):
            dup = (
                Inscripcion.objects.filter(
                    usuario=usuario,
                    clase=clase,
                    tipo=Inscripcion.Tipo.CLASE_SUELTA,
                )
                .exclude(estado=Inscripcion.Estado.CANCELADA)
                .first()
            )
            if dup:
                raise InscripcionDuplicada(dup)
            raise ReservaError("Ya tenés esa fecha reservada.")
    else:
        if clases_mensuales_cobrables(clase, periodo) <= 0:
            raise ReservaError(
                "No quedan clases de este horario en el mes elegido."
            )
        existing = (
            Inscripcion.objects.filter(
                usuario=usuario, clase=clase, periodo=periodo, tipo=tipo
            )
            .exclude(estado=Inscripcion.Estado.CANCELADA)
            .first()
        )
        if existing:
            raise InscripcionDuplicada(existing)

    if not permitir_sin_cupo and cupo_disponible(clase) <= 0:
        raise ClaseNoDisponible("No hay cupos disponibles.")

    return clase, tipo

# ── Core operations ───────────────────────────────────────────────────────────

def reservar_clase(usuario, clase_id, periodo, tipo, fecha_clase=None):
    """
    Entrypoint for the reservation process. Reserve a class spot for a user temporarily (PENDIENTE_PAGO), or add them to the FIFO waitlist.

    Business rules enforced:
    - User must have telefono_emergencia set.
    - Class must be in 'disponible' state.
    - No duplicate active inscription (re-registration after cancellation is allowed).
    - Concurrent reservations are serialised via select_for_update on the Class row.

    Returns:
        (Inscripcion, 'pendiente_pago') — spot was available and temporarily locked
        (Inscripcion, 'espera')   — added to waitlist
    """
    if not usuario.telefono_emergencia:
        raise TelefonoEmergenciaFaltante()

    with transaction.atomic():
        try:
            clase = Class.objects.select_for_update().get(id=clase_id)
        except Class.DoesNotExist as err:
            raise ClaseNoEncontrada() from err

        if clase.estado != 'disponible':
            raise ClaseNoDisponible()

        if tipo == Inscripcion.Tipo.CLASE_SUELTA:
            if not fecha_clase:
                raise ReservaError("Falta la fecha de la clase.")
            fecha_clase = timezone.localtime(fecha_clase)
            validar_intencion_inscripcion(
                usuario,
                clase_id,
                periodo,
                tipo,
                fecha_clase=fecha_clase,
                permitir_sin_cupo=True,
            )
            from apps.classes.ocurrencias import fecha_suelta_reservada

            if fecha_suelta_reservada(usuario, clase, fecha_clase):
                existing = (
                    Inscripcion.objects.filter(
                        usuario=usuario,
                        clase=clase,
                        tipo=tipo,
                    )
                    .exclude(estado=Inscripcion.Estado.CANCELADA)
                    .first()
                )
                if existing:
                    raise InscripcionDuplicada(existing)
        else:
            dup_filter = dict(usuario=usuario, clase=clase, periodo=periodo, tipo=tipo)
            existing = (
                Inscripcion.objects.filter(**dup_filter)
                .exclude(estado=Inscripcion.Estado.CANCELADA)
                .first()
            )
            if existing:
                raise InscripcionDuplicada(existing)

        create_kwargs = dict(
            usuario=usuario,
            clase=clase,
            periodo=periodo,
            tipo=tipo,
        )

        from apps.payments.periodos import requiere_precola_suelta

        forzar_espera = (
            tipo == Inscripcion.Tipo.CLASE_SUELTA and requiere_precola_suelta(periodo)
        )
        if cupo_disponible(clase) > 0 and not forzar_espera:
            inscripcion = Inscripcion.objects.create(
                **create_kwargs,
                estado=Inscripcion.Estado.PENDIENTE_PAGO,
            )
            if tipo == Inscripcion.Tipo.CLASE_SUELTA:
                from apps.classes.ocurrencias import crear_ocurrencia_suelta

                crear_ocurrencia_suelta(inscripcion, fecha_clase)
            return inscripcion, 'pendiente_pago'
        else:
            inscripcion = Inscripcion.objects.create(
                **create_kwargs,
                estado=Inscripcion.Estado.ESPERA,
            )
            if tipo == Inscripcion.Tipo.CLASE_SUELTA:
                from apps.classes.ocurrencias import crear_ocurrencia_suelta

                crear_ocurrencia_suelta(inscripcion, fecha_clase)
            return inscripcion, 'espera'


def _promover_lista_espera(clase):
    esperas = (
        Inscripcion.objects.select_for_update()
        .filter(clase=clase, estado=Inscripcion.Estado.ESPERA)
        .annotate(
            prioridad_tipo=Case(
                When(tipo=Inscripcion.Tipo.MENSUAL, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .order_by("prioridad_tipo", "fecha_inscripcion")
    )
    from apps.payments.periodos import requiere_precola_suelta

    for candidata in esperas:
        if (
            candidata.tipo == Inscripcion.Tipo.CLASE_SUELTA
            and requiere_precola_suelta(candidata.periodo)
        ):
            continue
        candidata.estado = Inscripcion.Estado.PENDIENTE_PAGO
        candidata.save(update_fields=["estado"])
        return candidata
    return None


def reconciliar_vencimientos_mensuales(fecha=None):
    """
    Cancela mensuales impagas vencidas del período vigente y libera cupos.
    Devuelve cantidad de inscripciones canceladas.
    """
    from apps.classes.ocurrencias import marcar_ocurrencias_inscripcion_canceladas
    from apps.payments.periodos import periodo_vigente, vencimiento_mensual_alcanzado

    hoy = fecha or timezone.localdate()
    vigente = periodo_vigente(hoy)
    if not vigente or not vencimiento_mensual_alcanzado(vigente, hoy):
        return 0

    with transaction.atomic():
        vencidas = list(
            Inscripcion.objects.select_for_update()
            .filter(
                periodo=vigente,
                tipo=Inscripcion.Tipo.MENSUAL,
                estado=Inscripcion.Estado.PENDIENTE_PAGO,
            )
            .select_related("clase")
            .order_by("fecha_inscripcion")
        )
        if not vencidas:
            return 0

        por_clase = {}
        for inscripcion in vencidas:
            por_clase[inscripcion.clase_id] = por_clase.get(inscripcion.clase_id, 0) + 1
            inscripcion.estado = Inscripcion.Estado.CANCELADA
            inscripcion.save(update_fields=["estado"])
            marcar_ocurrencias_inscripcion_canceladas(inscripcion)

        for clase_id, cantidad in por_clase.items():
            clase = Class.objects.select_for_update().get(pk=clase_id)
            for _ in range(cantidad):
                _promover_lista_espera(clase)

    return len(vencidas)


def reconciliar_vencimientos_sueltas():
    """
    Cancela reservas sueltas que quedaron en estado PENDIENTE_PAGO
    y ya pasaron su tiempo de gracia (default: 15 minutos).
    """
    from datetime import timedelta
    from django.conf import settings
    from apps.classes.ocurrencias import marcar_ocurrencias_inscripcion_canceladas
    from apps.payments.cancelaciones import cancelar_pagos_pendientes_inscripcion

    minutos = getattr(settings, "TIEMPO_GRACIA_PAGO_SUELTO_MINUTOS", 15)
    limite = timezone.now() - timedelta(minutes=minutos)

    with transaction.atomic():
        vencidas = list(
            Inscripcion.objects.select_for_update()
            .filter(
                tipo=Inscripcion.Tipo.CLASE_SUELTA,
                estado=Inscripcion.Estado.PENDIENTE_PAGO,
                fecha_inscripcion__lt=limite,
            )
            .select_related("clase")
            .order_by("fecha_inscripcion")
        )
        if not vencidas:
            return 0

        por_clase = {}
        for inscripcion in vencidas:
            por_clase[inscripcion.clase_id] = por_clase.get(inscripcion.clase_id, 0) + 1
            
            cancelar_pagos_pendientes_inscripcion(inscripcion)
            
            inscripcion.estado = Inscripcion.Estado.CANCELADA
            inscripcion.save(update_fields=["estado"])
            marcar_ocurrencias_inscripcion_canceladas(inscripcion)

        for clase_id, cantidad in por_clase.items():
            clase = Class.objects.select_for_update().get(pk=clase_id)
            for _ in range(cantidad):
                _promover_lista_espera(clase)

    return len(vencidas)


def _fecha_clase_inscripcion(inscripcion):
    from apps.classes.ocurrencias import primera_ocurrencia_activa

    return primera_ocurrencia_activa(inscripcion)


def cancelar_ocurrencia_mensual(inscripcion_id, usuario, fecha_clase):
    """
    Cancela una sesión concreta de una inscripción mensual.

    Con 48 h o más de anticipación otorga un crédito; si no, la clase se pierde.
    La inscripción mensual permanece activa.
    """
    from apps.payments.cancelaciones import (
        ResultadoCancelacion,
        anticipacion_suficiente_mensual,
        crear_credito_cancelacion,
    )

    fecha_clase = _normalizar_fecha_clase(fecha_clase)

    with transaction.atomic():
        try:
            inscripcion = Inscripcion.objects.select_for_update().get(
                id=inscripcion_id,
                usuario=usuario,
            )
        except Inscripcion.DoesNotExist as err:
            raise InscripcionNoEncontrada() from err

        if inscripcion.estado != Inscripcion.Estado.RESERVADA:
            raise ReservaError(
                "Solo podés cancelar clases de inscripciones confirmadas."
            )

        if inscripcion.tipo != Inscripcion.Tipo.MENSUAL:
            raise OcurrenciaNoValida()

        normalizada = _normalizar_fecha_clase(fecha_clase)
        if normalizada <= timezone.localtime(timezone.now()):
            raise ReservaError("No podés cancelar una clase que ya pasó.")

        try:
            ocurrencia = (
                InscripcionOcurrencia.objects.select_for_update()
                .get(
                    inscripcion=inscripcion,
                    fecha_clase=normalizada,
                )
            )
        except InscripcionOcurrencia.DoesNotExist as err:
            raise OcurrenciaNoValida() from err

        if ocurrencia.estado == InscripcionOcurrencia.Estado.CANCELADA:
            raise OcurrenciaYaCancelada()

        otorga_credito = anticipacion_suficiente_mensual(normalizada)
        credito = None
        if otorga_credito:
            credito = crear_credito_cancelacion(
                usuario,
                inscripcion.periodo,
                inscripcion.clase.disciplina,
            )

        ocurrencia.estado = InscripcionOcurrencia.Estado.CANCELADA
        ocurrencia.credito = credito
        ocurrencia.otorga_credito = otorga_credito
        ocurrencia.save(
            update_fields=["estado", "credito", "otorga_credito"]
        )

    if otorga_credito:
        mensaje = (
            "Clase cancelada. Te acreditamos un crédito para recuperarla "
            "en otro horario de la misma disciplina este mes."
        )
    else:
        mensaje = (
            "Clase cancelada. Pasadas las 48 h de anticipación, "
            "esa sesión se pierde sin reintegro."
        )

    return ResultadoCancelacion(
        inscripcion=inscripcion,
        otorga_credito=otorga_credito,
        mensaje=mensaje,
    )


def cancelar_reserva(inscripcion_id, usuario):
    """
    Cancela una reserva de clase suelta, abandona lista de espera,
    o anula una inscripción pendiente de pago.

    Para mensualidades confirmadas usá cancelar_ocurrencia_mensual().
    """
    from apps.payments.cancelaciones import (
        ResultadoCancelacion,
        anticipacion_suficiente_clase_suelta,
        reintegrar_pagos_inscripcion,
        cancelar_pagos_pendientes_inscripcion,
    )

    with transaction.atomic():
        try:
            inscripcion = Inscripcion.objects.select_for_update().get(
                id=inscripcion_id,
                usuario=usuario,
            )
        except Inscripcion.DoesNotExist as err:
            raise InscripcionNoEncontrada() from err

        if inscripcion.estado == Inscripcion.Estado.CANCELADA:
            raise InscripcionYaCancelada()

        if (
            inscripcion.tipo == Inscripcion.Tipo.MENSUAL
            and inscripcion.estado == Inscripcion.Estado.RESERVADA
        ):
            raise CancelacionMensualNoPermitida()

        era_reservada = inscripcion.estado in (
            Inscripcion.Estado.RESERVADA,
            Inscripcion.Estado.PENDIENTE_PAGO,
        )

        reembolsado = False
        mensaje = "Inscripción cancelada con éxito."

        if inscripcion.tipo == Inscripcion.Tipo.CLASE_SUELTA and era_reservada:
            fecha = _fecha_clase_inscripcion(inscripcion)
            if fecha and anticipacion_suficiente_clase_suelta(fecha):
                reembolsado = reintegrar_pagos_inscripcion(inscripcion)
                if reembolsado:
                    mensaje = (
                        "Reserva cancelada. Reintegraremos el pago de la seña "
                        "según el medio utilizado."
                    )
                else:
                    mensaje = "Reserva cancelada."
            elif fecha:
                mensaje = (
                    "Reserva cancelada. Con menos de 24 h de anticipación "
                    "la seña queda retenida."
                )

        cancelar_pagos_pendientes_inscripcion(inscripcion)
        
        inscripcion.estado = Inscripcion.Estado.CANCELADA
        inscripcion.save(update_fields=["estado"])

        from apps.classes.ocurrencias import marcar_ocurrencias_inscripcion_canceladas

        marcar_ocurrencias_inscripcion_canceladas(inscripcion)

        if era_reservada:
            _promover_lista_espera(inscripcion.clase)

    return ResultadoCancelacion(
        inscripcion=inscripcion,
        reembolsado=reembolsado,
        mensaje=mensaje,
    )
