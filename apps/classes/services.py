from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from .models import Class, Inscripcion


# ── Exceptions ────────────────────────────────────────────────────────────────

class ReservaError(Exception):
    pass


class TelefonoEmergenciaFaltante(ReservaError):
    pass


class ClaseNoDisponible(ReservaError):
    pass


class InscripcionDuplicada(ReservaError):
    pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def proxima_ocurrencia(clase):
    """Return the next future datetime for a weekly class (dia_semana + hora_inicio)."""
    if not clase.hora_inicio:
        return None
    ahora = timezone.localtime(timezone.now())
    tz = timezone.get_current_timezone()
    days_ahead = (clase.dia_semana - ahora.weekday()) % 7
    dt = timezone.make_aware(
        datetime.combine(ahora.date() + timedelta(days=days_ahead), clase.hora_inicio),
        tz,
    )
    if dt <= ahora:
        dt += timedelta(days=7)
    return dt


def cupo_disponible(clase):
    """Spots left: cupo_maximo minus active (RESERVADA + PENDIENTE_PAGO) inscriptions."""
    activas = clase.inscripciones.filter(
        estado__in=[Inscripcion.ESTADO_RESERVADA, Inscripcion.ESTADO_PENDIENTE_PAGO]
    ).count()
    return max(0, clase.cupo_maximo - activas)


# ── Core operations ───────────────────────────────────────────────────────────

def reservar_clase(usuario, clase_id):
    """
    Reserve a class spot for a user, or add them to the FIFO waitlist.

    Business rules enforced:
    - User must have telefono_emergencia set.
    - Class must be in 'disponible' state.
    - No duplicate active inscription (re-registration after cancellation is allowed).
    - Concurrent reservations are serialised via select_for_update on the Class row.

    Returns:
        (Inscripcion, 'reservada') — spot was available
        (Inscripcion, 'espera')   — added to waitlist
    """
    if not usuario.telefono_emergencia:
        raise TelefonoEmergenciaFaltante()

    with transaction.atomic():
        # Lock the class row so concurrent requests are serialised
        clase = Class.objects.select_for_update().get(id=clase_id)

        if clase.estado != 'disponible':
            raise ClaseNoDisponible()

        existing = (
            Inscripcion.objects.filter(usuario=usuario, clase=clase)
            .exclude(estado=Inscripcion.ESTADO_CANCELADA)
            .first()
        )
        if existing:
            raise InscripcionDuplicada(existing.estado)

        if cupo_disponible(clase) > 0:
            inscripcion = Inscripcion.objects.create(
                usuario=usuario,
                clase=clase,
                estado=Inscripcion.ESTADO_RESERVADA,
            )
            return inscripcion, 'reservada'
        else:
            inscripcion = Inscripcion.objects.create(
                usuario=usuario,
                clase=clase,
                estado=Inscripcion.ESTADO_ESPERA,
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
        except Inscripcion.DoesNotExist:
            raise ReservaError("Inscripción no encontrada.")

        if inscripcion.estado == Inscripcion.ESTADO_CANCELADA:
            raise ReservaError("La inscripción ya está cancelada.")

        era_reservada = inscripcion.estado in (
            Inscripcion.ESTADO_RESERVADA,
            Inscripcion.ESTADO_PENDIENTE_PAGO,
        )
        inscripcion.estado = Inscripcion.ESTADO_CANCELADA
        inscripcion.save()

        if era_reservada:
            primera_espera = (
                Inscripcion.objects.select_for_update()
                .filter(clase=inscripcion.clase, estado=Inscripcion.ESTADO_ESPERA)
                .order_by('fecha_inscripcion')
                .first()
            )
            if primera_espera:
                primera_espera.estado = Inscripcion.ESTADO_RESERVADA
                primera_espera.save()

    return inscripcion
