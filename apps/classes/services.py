from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.payments.models import PeriodoCobro

from .exceptions import (
    ClaseNoDisponible,
    ClaseNoEncontrada,
    InscripcionDuplicada,
    InscripcionNoEncontrada,
    InscripcionYaCancelada,
    PeriodoCobroInactivo,
    ReservaError,
    TelefonoEmergenciaFaltante,
)
from .models import Class, Inscripcion

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


def validar_intencion_inscripcion(usuario, clase_id, periodo, tipo, fecha_clase=None):
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
        dup_qs = Inscripcion.objects.filter(
            usuario=usuario,
            clase=clase,
            fecha_clase=_normalizar_fecha_clase(fecha_clase),
            tipo=Inscripcion.Tipo.CLASE_SUELTA,
        )
    else:
        if clases_mensuales_cobrables(clase, periodo) <= 0:
            raise ReservaError(
                "No quedan clases de este horario en el mes elegido."
            )
        dup_qs = Inscripcion.objects.filter(
            usuario=usuario, clase=clase, periodo=periodo, tipo=tipo
        )

    existing = dup_qs.exclude(estado=Inscripcion.Estado.CANCELADA).first()
    if existing:
        raise InscripcionDuplicada(existing)

    if cupo_disponible(clase) <= 0:
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
                usuario, clase_id, periodo, tipo, fecha_clase=fecha_clase
            )
            dup_filter = dict(
                usuario=usuario,
                clase=clase,
                fecha_clase=fecha_clase,
                tipo=tipo,
            )
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
        if tipo == Inscripcion.Tipo.CLASE_SUELTA:
            create_kwargs["fecha_clase"] = fecha_clase

        if cupo_disponible(clase) > 0:
            inscripcion = Inscripcion.objects.create(
                **create_kwargs,
                estado=Inscripcion.Estado.PENDIENTE_PAGO,
            )
            return inscripcion, 'pendiente_pago'
        else:
            inscripcion = Inscripcion.objects.create(
                **create_kwargs,
                estado=Inscripcion.Estado.ESPERA,
            )
            return inscripcion, 'espera'


def cancelar_reserva(inscripcion_id, usuario):
    """
    Cancel a reservation or leave the waitlist.

    If the cancelled inscription was RESERVADA/PENDIENTE_PAGO, the first
    ESPERA entry (FIFO by fecha_inscripcion) is automatically promoted.

    Returns the cancelled Inscripcion.
    """
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

        era_reservada = inscripcion.estado in (
            Inscripcion.Estado.RESERVADA,
            Inscripcion.Estado.PENDIENTE_PAGO,
        )
        inscripcion.estado = Inscripcion.Estado.CANCELADA
        inscripcion.save()

        if era_reservada:
            primera_espera = (
                Inscripcion.objects.select_for_update()
                .filter(clase=inscripcion.clase, estado=Inscripcion.Estado.ESPERA)
                .order_by('fecha_inscripcion')
                .first()
            )
            if primera_espera:
                primera_espera.estado = Inscripcion.Estado.PENDIENTE_PAGO
                primera_espera.save()

    return inscripcion
