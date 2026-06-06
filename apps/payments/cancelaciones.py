"""Reintegros y créditos por cancelación anticipada."""

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.classes.models import Inscripcion
from apps.payments.models import Credito, Pago, PagoInscripcion


@dataclass
class ResultadoCancelacion:
    inscripcion: Inscripcion
    otorga_credito: bool = False
    reembolsado: bool = False
    mensaje: str = ""


def horas_hasta_clase(fecha_clase):
    if fecha_clase is None:
        return None
    delta = timezone.localtime(fecha_clase) - timezone.localtime(timezone.now())
    return delta.total_seconds() / 3600


def anticipacion_suficiente_mensual(fecha_clase):
    horas = horas_hasta_clase(fecha_clase)
    if horas is None:
        return False
    minimo = getattr(settings, "CANCELACION_MENSUAL_HORAS_MIN", 48)
    return horas >= minimo


def anticipacion_suficiente_clase_suelta(fecha_clase):
    horas = horas_hasta_clase(fecha_clase)
    if horas is None:
        return False
    minimo = getattr(settings, "CANCELACION_CLASE_SUELTA_HORAS_MIN", 24)
    return horas >= minimo


def crear_credito_cancelacion(usuario, periodo, disciplina):
    return Credito.objects.create(
        usuario=usuario,
        periodo=periodo,
        disciplina=disciplina,
        estado=Credito.Estado.DISPONIBLE,
    )


def reintegrar_pagos_inscripcion(inscripcion):
    """Marca como reembolsados los pagos completados vinculados a la inscripción."""
    pagos_ids = (
        PagoInscripcion.objects.filter(
            inscripcion=inscripcion,
            pago__estado=Pago.Estado.COMPLETADO,
        )
        .values_list("pago_id", flat=True)
        .distinct()
    )
    if not pagos_ids:
        return False
    Pago.objects.filter(id__in=pagos_ids).update(estado=Pago.Estado.REEMBOLSADO)
    return True


def cancelar_pagos_pendientes_inscripcion(inscripcion):
    """Marca como fallidos los pagos pendientes vinculados a la inscripción."""
    pagos_ids = (
        PagoInscripcion.objects.filter(
            inscripcion=inscripcion,
            pago__estado=Pago.Estado.PENDIENTE,
        )
        .values_list("pago_id", flat=True)
        .distinct()
    )
    if pagos_ids:
        Pago.objects.filter(id__in=pagos_ids).update(estado=Pago.Estado.FALLIDO)


def aplicar_credito_automatico(inscripcion, usuario):
    """
    Consume 1 crédito si aplica a una clase suelta y descuenta lo pendiente.
    Retorna el monto aplicado (0 si no había crédito o nada pendiente).
    """
    from apps.payments.creditos import consumir_credito, valor_credito_disponible
    from apps.payments.inscripcion_pago import (
        precio_base_inscripcion,
        total_pagado_completado,
    )

    if inscripcion.tipo != Inscripcion.Tipo.CLASE_SUELTA:
        return Decimal("0")

    periodo = inscripcion.periodo
    disciplina = inscripcion.clase.disciplina
    valor_credito = valor_credito_disponible(usuario, periodo, disciplina)
    if valor_credito <= 0:
        return Decimal("0")

    base = precio_base_inscripcion(inscripcion)
    pagado = total_pagado_completado(inscripcion)
    pendiente = base - pagado
    if pendiente <= 0:
        return Decimal("0")

    monto_aplicado = min(valor_credito, pendiente).quantize(Decimal("0.01"))

    with transaction.atomic():
        consumir_credito(usuario, periodo, disciplina)
        pago = Pago.objects.create(
            usuario=usuario,
            periodo=periodo,
            monto=monto_aplicado,
            metodo=Pago.Metodo.CREDITO,
            estado=Pago.Estado.COMPLETADO,
        )
        PagoInscripcion.objects.create(
            pago=pago,
            inscripcion=inscripcion,
            monto_aplicado=monto_aplicado,
        )
        if pagado + monto_aplicado >= base:
            inscripcion.estado = Inscripcion.Estado.RESERVADA
        else:
            inscripcion.estado = Inscripcion.Estado.PENDIENTE_PAGO
        inscripcion.save(update_fields=["estado"])

    return monto_aplicado


def aplicar_pago_con_credito(inscripcion, usuario):
    """Compatibilidad: aplica el crédito automático sobre el saldo pendiente."""
    from apps.classes.exceptions import ReservaError

    monto = aplicar_credito_automatico(inscripcion, usuario)
    if monto <= 0:
        raise ReservaError(
            "No tenés créditos disponibles para esta disciplina en el período."
        )
    inscripcion.refresh_from_db()
    pago = (
        Pago.objects.filter(
            usuario=usuario,
            metodo=Pago.Metodo.CREDITO,
            estado=Pago.Estado.COMPLETADO,
            detalles__inscripcion=inscripcion,
        )
        .order_by("-pk")
        .first()
    )
    credito = (
        Credito.objects.filter(
            usuario=usuario,
            periodo=inscripcion.periodo,
            disciplina=inscripcion.clase.disciplina,
            estado=Credito.Estado.UTILIZADO,
        )
        .order_by("-pk")
        .first()
    )
    return pago, credito
