from .models import Inscripcion


class ReservaError(Exception):
    default_message = "No se pudo completar la reserva."

    def __init__(self, message=None):
        super().__init__(message or self.default_message)


class TelefonoEmergenciaFaltante(ReservaError):
    default_message = "Actualizá el teléfono de emergencia para reservar."


class ClaseNoEncontrada(ReservaError):
    default_message = "La clase no existe."


class ClaseNoDisponible(ReservaError):
    default_message = "La clase no está disponible."


class PeriodoCobroInactivo(ReservaError):
    default_message = "No hay un período de cobro activo configurado."


class InscripcionNoEncontrada(ReservaError):
    default_message = "Inscripción no encontrada."


class InscripcionYaCancelada(ReservaError):
    default_message = "La inscripción ya está cancelada."


class OcurrenciaYaCancelada(ReservaError):
    default_message = "Esa clase ya fue cancelada."


class OcurrenciaNoValida(ReservaError):
    default_message = "La fecha no corresponde a esta inscripción."


class CancelacionMensualNoPermitida(ReservaError):
    default_message = (
        "Para abonados mensuales, cancelá cada clase desde la lista de fechas."
    )


class InscripcionDuplicada(ReservaError):
    default_message = "Ya tenés una inscripción activa en esta clase."

    def __init__(self, inscripcion, message=None):
        self.inscripcion = inscripcion
        super().__init__(message)

    @property
    def pendiente_pago(self):
        return self.inscripcion.estado == Inscripcion.Estado.PENDIENTE_PAGO

    @property
    def en_lista_espera(self):
        return self.inscripcion.estado == Inscripcion.Estado.ESPERA

    @property
    def reservada(self):
        return self.inscripcion.estado == Inscripcion.Estado.RESERVADA
