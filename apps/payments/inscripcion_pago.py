from decimal import Decimal

from django.conf import settings
from django.db.models import Q, Sum

from apps.classes.models import Inscripcion
from apps.payments.models import Pago, PagoInscripcion, PrecioClase

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

        if (
            inscripcion.estado == Inscripcion.Estado.RESERVADA
            and inscripcion.tipo == Inscripcion.Tipo.MENSUAL
        ):
            from apps.classes.ocurrencias import generar_ocurrencias_mensual

            generar_ocurrencias_mensual(inscripcion)


def registrar_pago_efectivo(inscripcion, monto):
    """Crea un cobro en efectivo aprobado y aplica las reglas de negocio.

    Reutilizado por recepción al cobrar saldos pendientes (señas o pagos completos)
    sin pasar por el flujo de MercadoPago.
    """
    monto = Decimal(monto).quantize(Decimal("0.01"))
    pago = Pago.objects.create(
        usuario=inscripcion.usuario,
        periodo=inscripcion.periodo,
        monto=monto,
        metodo=Pago.Metodo.EFECTIVO,
        estado=Pago.Estado.PENDIENTE,
    )
    PagoInscripcion.objects.create(
        pago=pago,
        inscripcion=inscripcion,
        monto_aplicado=monto,
    )
    aplicar_pago_aprobado(pago)
    return pago


def precio_clase_periodo(clase, periodo):
    """Precio por clase en el período (una ocurrencia del horario semanal)."""
    try:
        return PrecioClase.objects.get(
            clase=clase,
            periodo=periodo,
        ).monto
    except PrecioClase.DoesNotExist:
        return Decimal(getattr(settings, "CLASE_DEFAULT_PRICE", "2500.0"))


def _desde_fecha_cobro(periodo, tipo):
    from apps.classes.services import desde_fecha_cobro_mensual

    if tipo == Inscripcion.Tipo.MENSUAL:
        return desde_fecha_cobro_mensual(periodo)
    from django.utils import timezone

    return timezone.localdate()


def precio_base_para_clase(clase, periodo, tipo):
    """Monto total a cobrar sin inscripción en BD (pantalla previa al pago)."""
    from apps.classes.services import ocurrencias_clase_en_periodo

    unitario = precio_clase_periodo(clase, periodo)
    if tipo == Inscripcion.Tipo.MENSUAL:
        cantidad = ocurrencias_clase_en_periodo(
            clase, periodo, desde_fecha=_desde_fecha_cobro(periodo, tipo)
        )
        return (unitario * cantidad).quantize(Decimal("0.01"))
    return unitario


def precio_base_inscripcion(inscripcion):
    from apps.classes.services import ocurrencias_clase_en_periodo

    unitario = precio_clase_periodo(
        inscripcion.clase, inscripcion.periodo
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
    unitario = precio_clase_periodo(clase, periodo)
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
    resumen = resumen_abono_mensual(clase, periodo, tipo=tipo)
    if resumen["cantidad_clases"] <= 0:
        return None
    return resumen


def resumen_abono_para_inscripcion(inscripcion):
    return resumen_abono_para_clase(
        inscripcion.clase, inscripcion.periodo, tipo=inscripcion.tipo
    )


def _monto_neto_con_credito(monto_bruto, valor_credito):
    if valor_credito <= 0 or monto_bruto <= 0:
        return monto_bruto, Decimal("0")
    aplicado = min(valor_credito, monto_bruto).quantize(Decimal("0.01"))
    neto = (monto_bruto - aplicado).quantize(Decimal("0.01"))
    return neto, aplicado


def resumen_credito_automatico(inscripcion, usuario):
    """Vista previa del crédito que se aplicará al confirmar el pago."""
    if usuario is None or inscripcion.tipo != Inscripcion.Tipo.CLASE_SUELTA:
        return {"aplica": False}

    from apps.payments.creditos import valor_credito_disponible

    valor = valor_credito_disponible(
        usuario, inscripcion.periodo, inscripcion.clase.disciplina
    )
    if valor <= 0:
        return {"aplica": False}

    base = precio_base_inscripcion(inscripcion)
    pagado = total_pagado_completado(inscripcion)
    pendiente = base - pagado
    if pendiente <= 0:
        return {"aplica": False}

    from apps.payments.creditos import creditos_disponibles_por_disciplina

    cantidad = creditos_disponibles_por_disciplina(usuario, inscripcion.periodo, inscripcion.clase.disciplina)
    monto = min(valor, pendiente).quantize(Decimal("0.01"))
    return {
        "aplica": True,
        "cantidad": cantidad,
        "monto": monto,
        "disciplina": inscripcion.clase.disciplina.nombre,
        "cubre_total": monto >= pendiente,
        "pendiente": pendiente,
    }


def resumen_credito_para_clase(clase, periodo, usuario):
    """Vista previa antes de crear la inscripción (clase suelta sin pagos previos)."""
    if usuario is None:
        return {"aplica": False}

    from apps.payments.creditos import valor_credito_disponible

    valor = valor_credito_disponible(usuario, periodo, clase.disciplina)
    if valor <= 0:
        return {"aplica": False}

    base = precio_base_para_clase(clase, periodo, Inscripcion.Tipo.CLASE_SUELTA)
    from apps.payments.creditos import creditos_disponibles_por_disciplina

    cantidad = creditos_disponibles_por_disciplina(usuario, periodo, clase.disciplina)
    monto = min(valor, base).quantize(Decimal("0.01"))
    return {
        "aplica": True,
        "cantidad": cantidad,
        "monto": monto,
        "disciplina": clase.disciplina.nombre,
        "cubre_total": monto >= base,
        "pendiente": base,
    }


def _opcion_pago(modalidad, monto_bruto, titulo, descripcion, valor_credito):
    monto, credito_aplicado = _monto_neto_con_credito(monto_bruto, valor_credito)
    opcion = {
        "modalidad": modalidad,
        "monto": monto,
        "titulo": titulo,
        "descripcion": descripcion,
    }
    if credito_aplicado > 0:
        opcion["monto_original"] = monto_bruto
        opcion["credito_aplicado"] = credito_aplicado
    return opcion


def _opciones_total_y_sena(valor_credito, base, titulo_total, desc_total, titulo_sena, desc_sena):
    """Clase suelta sin pagos previos: seña solo si no hay crédito a aplicar."""
    opciones = [
        _opcion_pago(
            "TOTAL",
            base,
            titulo_total,
            desc_total,
            valor_credito,
        ),
    ]
    if valor_credito <= 0:
        opciones.append(
            _opcion_pago(
                "SENA",
                monto_sena(base),
                titulo_sena,
                desc_sena,
                valor_credito,
            )
        )
    return opciones


def validar_modalidad_pago(inscripcion, usuario, modalidad):
    """Impide seña cuando hay crédito disponible para clase suelta."""
    modalidad = modalidad.upper()
    if modalidad != "SENA":
        return
    if inscripcion.tipo != Inscripcion.Tipo.CLASE_SUELTA:
        return
    if total_pagado_completado(inscripcion) > 0:
        return

    from apps.payments.creditos import valor_credito_disponible

    if valor_credito_disponible(
        usuario, inscripcion.periodo, inscripcion.clase.disciplina
    ) > 0:
        raise ValueError(
            "Con un crédito disponible no podés pagar solo la seña. "
            "Confirmá con pago total."
        )


def opciones_pago_para_clase(clase, periodo, tipo, usuario=None):
    """Opciones en pantalla de pago antes de crear la inscripción."""
    if tipo == Inscripcion.Tipo.MENSUAL:
        return []

    from apps.payments.creditos import valor_credito_disponible

    valor_credito = Decimal("0")
    if usuario is not None:
        valor_credito = valor_credito_disponible(usuario, periodo, clase.disciplina)

    base = precio_base_para_clase(clase, periodo, tipo)
    return _opciones_total_y_sena(
        valor_credito,
        base,
        "Pagar el total",
        "Un solo pago y tu clase queda reservada.",
        "Pagar seña (50%)",
        "Reservás con la mitad ahora; el resto antes de la clase.",
    )


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


def opciones_pago_inscripcion(inscripcion, usuario=None):
    """Opciones para clase suelta (seña/total). Abono mensual usa pantalla dedicada."""
    if inscripcion.estado != Inscripcion.Estado.PENDIENTE_PAGO:
        return []

    if inscripcion.tipo == Inscripcion.Tipo.MENSUAL:
        return []

    from apps.payments.creditos import valor_credito_disponible

    valor_credito = Decimal("0")
    if usuario is not None:
        valor_credito = valor_credito_disponible(
            usuario, inscripcion.periodo, inscripcion.clase.disciplina
        )

    resumen = resumen_pago_inscripcion(inscripcion)
    pagado = resumen["pagado"]
    opciones = []

    if resumen["mostrar_pagar_saldo"]:
        monto = monto_a_cobrar(inscripcion, "SALDO")
        opciones.append(
            _opcion_pago(
                "SALDO",
                monto,
                "Pagar saldo",
                f"Completá el saldo pendiente (ya pagaste ${pagado}).",
                valor_credito,
            )
        )
        return opciones

    if pagado == 0:
        return _opciones_total_y_sena(
            valor_credito,
            monto_a_cobrar(inscripcion, "TOTAL"),
            "Pago total",
            "Un solo pago para confirmar la clase.",
            "Seña (50%)",
            "Reservás con la mitad; el saldo después.",
        )

    opciones.append(
        _opcion_pago(
            "TOTAL",
            monto_a_cobrar(inscripcion, "TOTAL"),
            "Pago completo",
            "Confirmá tu inscripción.",
            valor_credito,
        )
    )
    return opciones


def monto_a_cobrar(inscripcion, modalidad):
    """modalidad: TOTAL, SENA o SALDO."""
    modalidad = modalidad.upper()
    if modalidad == "CREDITO":
        raise ValueError("Los créditos se aplican automáticamente al pagar.")

    base = precio_base_inscripcion(inscripcion)
    pagado = total_pagado_completado(inscripcion)

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
