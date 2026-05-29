from decimal import Decimal

from django.conf import settings
from django.db.models import Sum

from apps.classes.models import Inscripcion
from apps.payments.models import Pago, PagoInscripcion, PrecioDisciplina


def aplicar_pago_aprobado(pago):
    """Marca Pago completado y la inscripción RESERVADA (o sigue pendiente si fue seña)."""
    pago.estado = Pago.Estado.COMPLETADO
    pago.save(update_fields=["estado"])

    for detalle in pago.detalles.select_related("inscripcion"):
        inscripcion = detalle.inscripcion
        base_amount = precio_base_inscripcion(inscripcion)
        pagado = total_pagado_completado(inscripcion)

        if inscripcion.tipo == Inscripcion.Tipo.CLASE_SUELTA and pagado < base_amount:
            inscripcion.estado = Inscripcion.Estado.PENDIENTE_PAGO
        else:
            inscripcion.estado = Inscripcion.Estado.RESERVADA
        inscripcion.save(update_fields=["estado"])


def precio_base_inscripcion(inscripcion):
    try:
        return PrecioDisciplina.objects.get(
            disciplina=inscripcion.clase.disciplina,
            periodo=inscripcion.periodo,
        ).monto
    except PrecioDisciplina.DoesNotExist:
        return Decimal(getattr(settings, "CLASE_DEFAULT_PRICE", "2500.0"))


def monto_sena(base_amount):
    return base_amount / Decimal("2")


def total_pagado_completado(inscripcion):
    total = PagoInscripcion.objects.filter(
        inscripcion=inscripcion,
        pago__estado=Pago.Estado.COMPLETADO,
    ).aggregate(s=Sum("monto_aplicado"))["s"]
    return total or Decimal("0")


def resumen_pago_inscripcion(inscripcion):
    """Flags para mis_reservas y validación en pagar_inscripcion."""
    base = precio_base_inscripcion(inscripcion)
    pagado = total_pagado_completado(inscripcion)
    sena = monto_sena(base)
    saldo_restante = base - pagado

    if inscripcion.estado != Inscripcion.Estado.PENDIENTE_PAGO:
        return {
            "base": base,
            "pagado": pagado,
            "mostrar_pagar": False,
            "mostrar_pagar_saldo": False,
            "saldo_restante": Decimal("0"),
        }

    if (
        inscripcion.tipo == Inscripcion.Tipo.CLASE_SUELTA
        and pagado >= sena
        and pagado < base
    ):
        return {
            "base": base,
            "pagado": pagado,
            "mostrar_pagar": False,
            "mostrar_pagar_saldo": True,
            "saldo_restante": saldo_restante,
        }

    return {
        "base": base,
        "pagado": pagado,
        "mostrar_pagar": saldo_restante > 0,
        "mostrar_pagar_saldo": False,
        "saldo_restante": saldo_restante,
    }


def pago_pendiente(inscripcion, monto):
    return (
        Pago.objects.filter(
            estado=Pago.Estado.PENDIENTE,
            detalles__inscripcion=inscripcion,
            monto=monto,
        )
        .distinct()
        .order_by("-pk")
        .first()
    )


def _anular_otros_pendientes(inscripcion, excepto_pago_id=None):
    qs = Pago.objects.filter(
        estado=Pago.Estado.PENDIENTE,
        detalles__inscripcion=inscripcion,
    )
    if excepto_pago_id is not None:
        qs = qs.exclude(pk=excepto_pago_id)
    qs.update(estado=Pago.Estado.FALLIDO)


def preparar_pago_mercadopago(inscripcion, usuario, monto):
    """Reutiliza un Pago PENDIENTE (mismo monto) o crea uno nuevo; anula otros pendientes."""
    pago = pago_pendiente(inscripcion, monto)
    if pago:
        _anular_otros_pendientes(inscripcion, excepto_pago_id=pago.pk)
        return pago

    _anular_otros_pendientes(inscripcion)
    pago = Pago.objects.create(
        usuario=usuario,
        periodo=inscripcion.periodo,
        monto=monto,
        metodo=Pago.Metodo.MERCADOPAGO,
        estado=Pago.Estado.PENDIENTE,
    )
    PagoInscripcion.objects.create(
        pago=pago,
        inscripcion=inscripcion,
        monto_aplicado=monto,
    )
    return pago


def monto_a_cobrar(inscripcion, modalidad):
    """modalidad: TOTAL, SENA o SALDO."""
    base = precio_base_inscripcion(inscripcion)
    pagado = total_pagado_completado(inscripcion)
    modalidad = modalidad.upper()

    if modalidad == "SALDO":
        if inscripcion.tipo != Inscripcion.Tipo.CLASE_SUELTA:
            raise ValueError("SALDO solo aplica a clase suelta.")
        if pagado < monto_sena(base):
            raise ValueError("No hay seña pagada.")
        return base - pagado

    if modalidad == "SENA":
        if inscripcion.tipo != Inscripcion.Tipo.CLASE_SUELTA:
            return base - pagado
        if pagado > 0:
            raise ValueError("Ya hay un pago registrado.")
        return monto_sena(base)

    return base - pagado
