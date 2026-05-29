from decimal import Decimal

from django.conf import settings
from django.db.models import Q, Sum

from apps.classes.models import Inscripcion
from apps.payments.models import Pago, PagoInscripcion, PrecioDisciplina

PAGO_PENDIENTE_SESSION = "pago_pendiente"


def guardar_intencion_pago(
    request, *, clase_id, periodo_id, tipo, fecha_clase=None
):
    payload = {
        "clase_id": clase_id,
        "periodo_id": periodo_id,
        "tipo": tipo,
    }
    if fecha_clase is not None:
        from apps.classes.services import _normalizar_fecha_clase

        payload["fecha_clase"] = _normalizar_fecha_clase(fecha_clase).isoformat()
    request.session[PAGO_PENDIENTE_SESSION] = payload
    request.session.modified = True


def fecha_clase_desde_intencion(data):
    from django.utils.dateparse import parse_datetime

    from django.utils import timezone

    raw = data.get("fecha_clase")
    if not raw:
        return None
    dt = parse_datetime(raw)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    from apps.classes.services import _normalizar_fecha_clase

    return _normalizar_fecha_clase(dt)


def intencion_pago_para_clase(request, clase_id):
    data = request.session.get(PAGO_PENDIENTE_SESSION)
    if data and data.get("clase_id") == clase_id:
        return data
    return None


def limpiar_intencion_pago(request):
    request.session.pop(PAGO_PENDIENTE_SESSION, None)
    request.session.modified = True


def inscripcion_tiene_intento_pago(inscripcion):
    return PagoInscripcion.objects.filter(inscripcion=inscripcion).exists()


def filtro_inscripciones_en_reservas():
    """Excluye PENDIENTE_PAGO huérfanas (sin Pago) de datos viejos."""
    return (
        Q(estado__in=(Inscripcion.Estado.RESERVADA, Inscripcion.Estado.ESPERA))
        | Q(
            estado=Inscripcion.Estado.PENDIENTE_PAGO,
            pk__in=PagoInscripcion.objects.values("inscripcion_id"),
        )
    )


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


def precio_disciplina_periodo(disciplina, periodo):
    """Precio por clase en el período (una ocurrencia del horario semanal)."""
    try:
        return PrecioDisciplina.objects.get(
            disciplina=disciplina,
            periodo=periodo,
        ).monto
    except PrecioDisciplina.DoesNotExist:
        return Decimal(getattr(settings, "CLASE_DEFAULT_PRICE", "2500.0"))


def _desde_fecha_cobro(periodo, tipo):
    from django.utils import timezone

    hoy = timezone.localdate()
    if tipo == Inscripcion.Tipo.MENSUAL and hoy < periodo.fecha_inicio_periodo:
        return periodo.fecha_inicio_periodo
    return hoy


def precio_base_para_clase(clase, periodo, tipo):
    """Monto total a cobrar sin inscripción en BD (pantalla previa al pago)."""
    from apps.classes.services import ocurrencias_clase_en_periodo

    unitario = precio_disciplina_periodo(clase.disciplina, periodo)
    if tipo == Inscripcion.Tipo.MENSUAL:
        cantidad = ocurrencias_clase_en_periodo(
            clase, periodo, desde_fecha=_desde_fecha_cobro(periodo, tipo)
        )
        return (unitario * cantidad).quantize(Decimal("0.01"))
    return unitario


def precio_base_inscripcion(inscripcion):
    from apps.classes.services import ocurrencias_clase_en_periodo

    unitario = precio_disciplina_periodo(
        inscripcion.clase.disciplina, inscripcion.periodo
    )
    if inscripcion.tipo == Inscripcion.Tipo.MENSUAL:
        cantidad = ocurrencias_clase_en_periodo(
            inscripcion.clase,
            inscripcion.periodo,
            desde_fecha=_desde_fecha_cobro(inscripcion.periodo, inscripcion.tipo),
        )
        return (unitario * cantidad).quantize(Decimal("0.01"))
    return unitario


def resumen_abono_mensual(clase, periodo, desde_fecha=None, tipo=None):
    """Clases del horario en el período y total = precio × cantidad."""
    from apps.classes.services import ocurrencias_clase_en_periodo

    if desde_fecha is None and tipo is not None:
        desde_fecha = _desde_fecha_cobro(periodo, tipo)
    unitario = precio_disciplina_periodo(clase.disciplina, periodo)
    cantidad = ocurrencias_clase_en_periodo(clase, periodo, desde_fecha)
    total = (unitario * cantidad).quantize(Decimal("0.01"))
    return {
        "cantidad_clases": cantidad,
        "precio_unitario": unitario,
        "precio_total": total,
    }


def resumen_abono_para_clase(clase, periodo, tipo):
    if tipo != Inscripcion.Tipo.MENSUAL:
        return None
    return resumen_abono_mensual(clase, periodo, tipo=tipo)


def resumen_abono_para_inscripcion(inscripcion):
    return resumen_abono_para_clase(
        inscripcion.clase, inscripcion.periodo, tipo=inscripcion.tipo
    )


def opciones_pago_para_clase(clase, periodo, tipo):
    """Opciones en pantalla de pago antes de crear la inscripción."""
    if tipo == Inscripcion.Tipo.MENSUAL:
        return []

    base = precio_base_para_clase(clase, periodo, tipo)
    sena = monto_sena(base)
    return [
        {
            "modalidad": "TOTAL",
            "monto": base,
            "titulo": "Pagar el total",
            "descripcion": "Un solo pago y tu clase queda reservada.",
        },
        {
            "modalidad": "SENA",
            "monto": sena,
            "titulo": "Pagar seña (50%)",
            "descripcion": "Reservás con la mitad ahora; el resto antes de la clase.",
        },
    ]


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


def opciones_pago_inscripcion(inscripcion):
    """Opciones para clase suelta (seña/total). Abono mensual usa pantalla dedicada."""
    if inscripcion.estado != Inscripcion.Estado.PENDIENTE_PAGO:
        return []

    if inscripcion.tipo == Inscripcion.Tipo.MENSUAL:
        return []

    resumen = resumen_pago_inscripcion(inscripcion)
    pagado = resumen["pagado"]

    if resumen["mostrar_pagar_saldo"]:
        monto = monto_a_cobrar(inscripcion, "SALDO")
        return [
            {
                "modalidad": "SALDO",
                "monto": monto,
                "titulo": "Pagar saldo",
                "descripcion": f"Completá los ${monto} restantes (ya pagaste ${pagado}).",
            }
        ]

    if pagado == 0:
        return [
            {
                "modalidad": "TOTAL",
                "monto": monto_a_cobrar(inscripcion, "TOTAL"),
                "titulo": "Pago total",
                "descripcion": "Un solo pago para confirmar la clase.",
            },
            {
                "modalidad": "SENA",
                "monto": monto_a_cobrar(inscripcion, "SENA"),
                "titulo": "Seña (50%)",
                "descripcion": "Reservás con la mitad; el saldo después.",
            },
        ]

    return [
        {
            "modalidad": "TOTAL",
            "monto": monto_a_cobrar(inscripcion, "TOTAL"),
            "titulo": "Pago completo",
            "descripcion": "Confirmá tu inscripción.",
        }
    ]


def monto_a_cobrar(inscripcion, modalidad):
    """modalidad: TOTAL, SENA o SALDO."""
    base = precio_base_inscripcion(inscripcion)
    pagado = total_pagado_completado(inscripcion)
    modalidad = modalidad.upper()

    if inscripcion.tipo == Inscripcion.Tipo.MENSUAL:
        if modalidad != "TOTAL":
            raise ValueError("El abono mensual solo admite pago total.")
        return base - pagado

    if modalidad == "SALDO":
        if pagado < monto_sena(base):
            raise ValueError("No hay seña pagada.")
        return base - pagado

    if modalidad == "SENA":
        if pagado > 0:
            raise ValueError("Ya hay un pago registrado.")
        return monto_sena(base)

    return base - pagado
