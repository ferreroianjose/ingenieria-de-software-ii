from collections import OrderedDict

from decimal import Decimal

from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from GYMFlow.access import staff_required

from apps.classes import services as class_services
from apps.classes.flow import build_flow_stepper_context
from apps.classes.exceptions import InscripcionDuplicada, ReservaError
from apps.classes.models import Class, Inscripcion, InscripcionOcurrencia
from apps.payments.inscripcion_pago import (
    fecha_clase_desde_intencion,
    intencion_pago_para_clase,
    limpiar_intencion_pago,
    monto_a_cobrar,
    opciones_pago_inscripcion,
    opciones_pago_para_clase,
    precio_disciplina_periodo,
    preparar_pago_mercadopago,
    resumen_abono_para_clase,
    resumen_abono_para_inscripcion,
    resumen_credito_automatico,
    resumen_credito_para_clase,
    validar_modalidad_pago,
)
from apps.payments.models import Pago, PeriodoCobro
from apps.payments.services import ConfirmacionMP, mercadopago_service
from apps.payments.webhook_verify import verify_mercadopago_webhook


@staff_required
def staff_pagos(request):
    return render(request, "payments/manage.html")


@login_required
def mis_pagos(request):
    pagos = (
        Pago.objects.filter(usuario=request.user)
        .select_related("periodo")
        .prefetch_related(
            "detalles__inscripcion__clase__disciplina",
            "detalles__inscripcion__clase__sala__sede",
        )
        .order_by("-fecha_pago")
    )

    estado_meta = {
        Pago.Estado.COMPLETADO: {"level": "success", "label": "Completado"},
        Pago.Estado.PENDIENTE: {"level": "warning", "label": "Pendiente"},
        Pago.Estado.FALLIDO: {"level": "error", "label": "Fallido"},
        Pago.Estado.REEMBOLSADO: {"level": "info", "label": "Reembolsado"},
    }

    pagos_por_periodo = OrderedDict()
    for pago in pagos:
        meta = estado_meta.get(
            pago.estado,
            {"level": "info", "label": pago.get_estado_display()},
        )
        detalles_ui = []
        for detalle in pago.detalles.all():
            inscripcion = detalle.inscripcion
            es_mensual = inscripcion.tipo == Inscripcion.Tipo.MENSUAL
            unitario = precio_disciplina_periodo(
                inscripcion.clase.disciplina,
                inscripcion.periodo,
            )

            if es_mensual:
                desde = max(
                    inscripcion.periodo.fecha_inicio_periodo,
                    pago.fecha_pago.date(),
                )
                ocurrencias_qs = inscripcion.ocurrencias.filter(
                    estado=InscripcionOcurrencia.Estado.ACTIVA,
                    fecha_clase__date__gte=desde,
                ).order_by("fecha_clase")
                ocurrencias = [o.fecha_clase for o in ocurrencias_qs]
                if not ocurrencias:
                    ocurrencias = class_services.ocurrencias_detalle_en_periodo(
                        inscripcion.clase,
                        inscripcion.periodo,
                        desde_fecha=desde,
                    )
            else:
                ocurrencia = (
                    inscripcion.ocurrencias.filter(
                        estado=InscripcionOcurrencia.Estado.ACTIVA
                    )
                    .order_by("fecha_clase")
                    .values_list("fecha_clase", flat=True)
                    .first()
                )
                if not ocurrencia:
                    ocurrencia = class_services.proxima_ocurrencia(inscripcion.clase)
                ocurrencias = [ocurrencia] if ocurrencia else []

            clase = inscripcion.clase
            sala = clase.sala
            ubicacion = sala.nombre if sala else ""
            if clase.hora_inicio:
                horario_label = (
                    f"{clase.get_dia_semana_display()} "
                    f"{clase.hora_inicio.strftime('%H:%M')} hs"
                )
            else:
                horario_label = clase.get_dia_semana_display()

            detalles_ui.append(
                {
                    "disciplina": clase.disciplina.nombre,
                    "ubicacion": ubicacion,
                    "tipo_label": "Mensualidad" if es_mensual else "Clase individual",
                    "es_mensual": es_mensual,
                    "horario_label": horario_label,
                    "precio_unitario": unitario,
                    "ocurrencias": ocurrencias,
                    "subtotal": (
                        (unitario * Decimal(len(ocurrencias))).quantize(
                            Decimal("0.01")
                        )
                        if es_mensual
                        else detalle.monto_aplicado
                    ),
                }
            )

        pago_item = {
            "id": pago.id,
            "periodo": pago.periodo.nombre,
            "fecha": pago.fecha_pago,
            "metodo": pago.get_metodo_display(),
            "monto": pago.monto,
            "estado_label": meta["label"],
            "estado_level": meta["level"],
            "detalles": detalles_ui,
        }
        periodo_nombre = pago.periodo.nombre
        if periodo_nombre not in pagos_por_periodo:
            pagos_por_periodo[periodo_nombre] = {
                "periodo": periodo_nombre,
                "pagos": [],
                "total_monto": Decimal("0"),
            }
        pagos_por_periodo[periodo_nombre]["pagos"].append(pago_item)
        pagos_por_periodo[periodo_nombre]["total_monto"] += pago.monto

    return render(
        request,
        "payments/mis_pagos.html",
        {
            "pagos_por_periodo": list(pagos_por_periodo.values()),
            "flow_title": "Mis pagos",
            "flow_subtitle": "Consultá el estado de tus pagos y tu historial de cobros.",
        },
    )


def _contexto_seleccion_pago(
    request,
    *,
    clase,
    periodo,
    tipo,
    abono_resumen,
    opciones,
    pagar_url,
    fecha_clase=None,
    credito_auto=None,
):
    actividades_url = reverse("classes:actividades")
    horarios_url = reverse("classes:cronograma", args=[clase.disciplina_id])
    clase_url = reverse("classes:detalle", args=[clase.id])
    pago_url = request.path
    request.session["flow_disciplina_id"] = clase.disciplina_id
    request.session["flow_clase_disciplina_id"] = clase.disciplina_id
    request.session["flow_clase_id"] = clase.id
    request.session["flow_pago_url"] = pago_url
    return {
        "clase": clase,
        "periodo": periodo,
        "fecha_clase": fecha_clase,
        "es_inscripcion_mensual": tipo == Inscripcion.Tipo.MENSUAL,
        "opciones": opciones,
        "abono_resumen": {
            **abono_resumen,
            "precio_total_con_credito": (
                (abono_resumen["precio_total"] - credito_auto["monto"]).quantize(Decimal("0.01"))
                if abono_resumen and credito_auto and credito_auto.get("aplica")
                else None
            ),
        } if abono_resumen else None,
        "credito_auto": credito_auto,
        "pagar_url": pagar_url,
        "flow_step": "pago",
        "flow_back_url": reverse("classes:detalle", args=[clase.id]),
        "flow_back_label": "Volver a la clase",
        "flow_title": "Confirmar pago",
        "flow_subtitle": (
            "Revisá el total y completá el pago en Mercado Pago para asegurar tu lugar."
            if abono_resumen
            else "Elegí cómo pagar. Tu reserva se confirma cuando se acredite el pago."
        ),
        **build_flow_stepper_context(
            "pago",
            actividades_url=actividades_url,
            horarios_url=horarios_url,
            clase_url=clase_url,
            pago_url=pago_url,
        ),
    }


@login_required
def seleccion_pago_clase(request, clase_id):
    data = intencion_pago_para_clase(request, clase_id)
    if not data:
        messages.info(
            request, "Elegí la modalidad de inscripción para continuar al pago."
        )
        return redirect("classes:detalle", clase_id=clase_id)

    clase = get_object_or_404(
        Class.objects.select_related("disciplina"),
        pk=clase_id,
        estado="disponible",
    )
    periodo = get_object_or_404(PeriodoCobro, pk=data["periodo_id"])
    tipo = data["tipo"]
    fecha_clase = fecha_clase_desde_intencion(data)

    try:
        periodo = class_services.resolver_periodo_inscripcion(
            periodo.id, tipo, fecha_clase=fecha_clase
        )
        class_services.validar_intencion_inscripcion(
            request.user, clase_id, periodo, tipo, fecha_clase=fecha_clase
        )
    except InscripcionDuplicada as exc:
        from apps.payments.inscripcion_pago import inscripcion_tiene_intento_pago

        if exc.pendiente_pago and inscripcion_tiene_intento_pago(exc.inscripcion):
            limpiar_intencion_pago(request)
            return redirect(
                "payments:seleccion_pago", inscripcion_id=exc.inscripcion.id
            )
        messages.warning(request, str(exc))
        limpiar_intencion_pago(request)
        return redirect("classes:detalle", clase_id=clase_id)
    except ReservaError as exc:
        messages.error(request, str(exc))
        limpiar_intencion_pago(request)
        return redirect("classes:detalle", clase_id=clase_id)

    abono_resumen = resumen_abono_para_clase(clase, periodo, tipo)
    if tipo == Inscripcion.Tipo.MENSUAL and not abono_resumen:
        messages.error(
            request, "No quedan clases de este horario en el mes elegido."
        )
        limpiar_intencion_pago(request)
        return redirect("classes:detalle", clase_id=clase_id)

    opciones = opciones_pago_para_clase(clase, periodo, tipo, usuario=request.user)
    credito_auto = resumen_credito_para_clase(clase, periodo, request.user)
    pagar_url = reverse("payments:pagar_clase", args=[clase_id])
    return render(
        request,
        "payments/seleccion_pago.html",
        _contexto_seleccion_pago(
            request,
            clase=clase,
            periodo=periodo,
            tipo=tipo,
            abono_resumen=abono_resumen,
            opciones=opciones,
            pagar_url=pagar_url,
            fecha_clase=fecha_clase,
            credito_auto=credito_auto,
        ),
    )


def _mensaje_credito_aplicado(monto_credito, inscripcion):
    if monto_credito <= 0:
        return None
    if inscripcion.estado == Inscripcion.Estado.RESERVADA:
        return (
            f"Clase reservada. Se aplicó tu crédito automáticamente "
            f"(${monto_credito})."
        )
    return (
        f"Se aplicó tu crédito (${monto_credito}). "
        "Completá el pago restante en Mercado Pago."
    )


def _aplicar_credito_y_cobrar(request, inscripcion, modalidad):
    """Aplica crédito automático y retorna monto pendiente en Mercado Pago."""
    from apps.classes.exceptions import ReservaError
    from apps.payments.cancelaciones import aplicar_credito_automatico

    if modalidad == "CREDITO":
        modalidad = "TOTAL"

    try:
        validar_modalidad_pago(inscripcion, request.user, modalidad)
    except ValueError as exc:
        return None, exc

    try:
        monto_credito = aplicar_credito_automatico(inscripcion, request.user)
    except ReservaError as exc:
        return None, exc

    inscripcion.refresh_from_db()
    mensaje_credito = _mensaje_credito_aplicado(monto_credito, inscripcion)

    if inscripcion.estado == Inscripcion.Estado.RESERVADA:
        return Decimal("0"), mensaje_credito

    try:
        amount_to_pay = monto_a_cobrar(inscripcion, modalidad)
    except ValueError as exc:
        return None, exc

    return amount_to_pay, mensaje_credito


@login_required
def pagar_clase(request, clase_id):
    if request.method != "POST":
        return redirect("payments:seleccion_pago_clase", clase_id=clase_id)

    data = intencion_pago_para_clase(request, clase_id)
    if not data:
        messages.info(
            request, "Elegí la modalidad de inscripción para continuar al pago."
        )
        return redirect("classes:detalle", clase_id=clase_id)

    periodo = get_object_or_404(PeriodoCobro, pk=data["periodo_id"])
    tipo = data["tipo"]
    fecha_clase = fecha_clase_desde_intencion(data)
    modalidad = request.POST.get("modalidad", "TOTAL").upper()
    fallo = redirect("payments:seleccion_pago_clase", clase_id=clase_id)

    try:
        periodo = class_services.resolver_periodo_inscripcion(
            periodo.id, tipo, fecha_clase=fecha_clase
        )
        class_services.validar_intencion_inscripcion(
            request.user, clase_id, periodo, tipo, fecha_clase=fecha_clase
        )
        inscripcion, _ = class_services.reservar_clase(
            request.user,
            clase_id,
            periodo=periodo,
            tipo=tipo,
            fecha_clase=fecha_clase,
        )
    except InscripcionDuplicada as exc:
        from apps.payments.inscripcion_pago import inscripcion_tiene_intento_pago

        limpiar_intencion_pago(request)
        if exc.pendiente_pago and inscripcion_tiene_intento_pago(exc.inscripcion):
            return redirect(
                "payments:seleccion_pago", inscripcion_id=exc.inscripcion.id
            )
        messages.warning(request, str(exc))
        return redirect("classes:detalle", clase_id=clase_id)
    except (ReservaError, ValueError) as exc:
        messages.error(request, str(exc))
        return fallo

    amount_to_pay, resultado = _aplicar_credito_y_cobrar(
        request, inscripcion, modalidad
    )
    if isinstance(resultado, Exception):
        try:
            class_services.cancelar_reserva(inscripcion.id, request.user)
        except ReservaError:
            pass
        messages.error(request, str(resultado))
        return fallo

    inscripcion.refresh_from_db()
    if inscripcion.estado == Inscripcion.Estado.RESERVADA:
        limpiar_intencion_pago(request)
        messages.success(
            request,
            resultado or "Clase reservada con tu crédito.",
        )
        return redirect("classes:mis_reservas")

    if amount_to_pay <= 0:
        if tipo == Inscripcion.Tipo.MENSUAL:
            messages.error(
                request, "No quedan clases de este horario en el mes elegido."
            )
        else:
            messages.info(request, "No hay monto pendiente de pago.")
        limpiar_intencion_pago(request)
        return redirect("classes:detalle", clase_id=clase_id)

    if resultado:
        messages.info(request, resultado)

    pago = preparar_pago_mercadopago(inscripcion, request.user, amount_to_pay)
    init_point = mercadopago_service.create_preference(pago, request)
    limpiar_intencion_pago(request)

    if not init_point:
        messages.error(
            request, "Pago fallido por error al intentar conectar al servidor"
        )
        return redirect("payments:seleccion_pago", inscripcion_id=inscripcion.id)

    return redirect(init_point)


@login_required
def seleccion_pago(request, inscripcion_id):
    inscripcion = get_object_or_404(
        Inscripcion.objects.select_related("clase", "clase__disciplina"),
        id=inscripcion_id,
        usuario=request.user,
    )

    if inscripcion.estado == Inscripcion.Estado.RESERVADA:
        messages.info(request, "Esta clase ya está reservada.")
        return redirect("classes:mis_reservas")

    if inscripcion.estado != Inscripcion.Estado.PENDIENTE_PAGO:
        messages.warning(request, "Esta inscripción no requiere pago en este momento.")
        return redirect("classes:detalle", clase_id=inscripcion.clase_id)

    abono_resumen = resumen_abono_para_inscripcion(inscripcion)
    opciones = opciones_pago_inscripcion(inscripcion, usuario=request.user)
    if abono_resumen is None and not opciones:
        if inscripcion.tipo == Inscripcion.Tipo.MENSUAL:
            messages.error(
                request, "No quedan clases de este horario en el mes elegido."
            )
            return redirect("classes:detalle", clase_id=inscripcion.clase_id)
        messages.info(request, "Esta inscripción ya está paga.")
        return redirect("classes:mis_reservas")

    pagar_url = reverse("payments:pagar", args=[inscripcion.id])
    credito_auto = resumen_credito_automatico(inscripcion, request.user)
    return render(
        request,
        "payments/seleccion_pago.html",
        _contexto_seleccion_pago(
            request,
            clase=inscripcion.clase,
            periodo=inscripcion.periodo,
            tipo=inscripcion.tipo,
            abono_resumen=abono_resumen,
            opciones=opciones,
            pagar_url=pagar_url,
            credito_auto=credito_auto,
        ),
    )


@login_required
def pagar_inscripcion(request, inscripcion_id):
    if request.method != "POST":
        return redirect("payments:seleccion_pago", inscripcion_id=inscripcion_id)

    inscripcion = get_object_or_404(Inscripcion, id=inscripcion_id, usuario=request.user)

    if inscripcion.estado == Inscripcion.Estado.RESERVADA:
        messages.info(request, "Esta clase ya está reservada.")
        return redirect("classes:mis_reservas")

    modalidad = request.POST.get("modalidad", "TOTAL").upper()
    fallo = redirect("payments:seleccion_pago", inscripcion_id=inscripcion_id)

    amount_to_pay, resultado = _aplicar_credito_y_cobrar(
        request, inscripcion, modalidad
    )
    if isinstance(resultado, Exception):
        messages.error(request, str(resultado))
        return fallo

    inscripcion.refresh_from_db()
    if inscripcion.estado == Inscripcion.Estado.RESERVADA:
        messages.success(
            request,
            resultado or "Clase reservada con tu crédito.",
        )
        return redirect("classes:mis_reservas")

    if amount_to_pay <= 0:
        messages.info(request, "Esta inscripción ya está paga.")
        return redirect("classes:mis_reservas")

    if resultado:
        messages.info(request, resultado)

    pago = preparar_pago_mercadopago(inscripcion, request.user, amount_to_pay)
    init_point = mercadopago_service.create_preference(pago, request)

    if not init_point:
        messages.error(request, "Pago fallido por error al intentar conectar al servidor")
        return redirect("payments:seleccion_pago", inscripcion_id=inscripcion_id)

    return redirect(init_point)


def _mp_payment_id_from_request(request):
    return request.GET.get("payment_id") or request.GET.get("collection_id")


def _retorno_checkout(request, pago_id, *, marcar_fallido_si_rechazado):
    pago = get_object_or_404(Pago, id=pago_id, usuario=request.user)
    destino = redirect("classes:mis_reservas")

    if pago.estado == Pago.Estado.COMPLETADO:
        messages.success(request, "Pago exitoso")
        return destino

    mp_payment_id = _mp_payment_id_from_request(request)
    if not mp_payment_id:
        if marcar_fallido_si_rechazado:
            messages.error(request, "Pago fallido. Por favor intente nuevamente.")
        else:
            messages.info(
                request,
                "Estamos confirmando tu pago. Si ya pagaste, la reserva se actualizará en breve.",
            )
        return destino

    resultado = mercadopago_service.confirmar_pago_desde_mp(mp_payment_id, pago.id)
    if resultado in (ConfirmacionMP.APPROVED, ConfirmacionMP.ALREADY_COMPLETED):
        messages.success(request, "Pago exitoso")
    elif resultado == ConfirmacionMP.PENDING:
        messages.info(
            request,
            "Tu pago está en proceso. Te avisaremos cuando se confirme.",
        )
    elif resultado == ConfirmacionMP.REJECTED and marcar_fallido_si_rechazado:
        pago.estado = Pago.Estado.FALLIDO
        pago.save(update_fields=["estado"])
        messages.error(request, "Pago fallido. Por favor intente nuevamente.")
    elif resultado == ConfirmacionMP.REJECTED:
        messages.error(request, "El pago no pudo ser completado.")
    else:
        messages.error(
            request,
            "Pago fallido. Por favor intente nuevamente."
            if marcar_fallido_si_rechazado
            else "El pago no pudo ser completado.",
        )

    return destino


@login_required
def success(request, pago_id):
    return _retorno_checkout(request, pago_id, marcar_fallido_si_rechazado=False)


@login_required
def failure(request, pago_id):
    return _retorno_checkout(request, pago_id, marcar_fallido_si_rechazado=True)


@csrf_exempt
@require_POST
def mercadopago_webhook(request):
    if not verify_mercadopago_webhook(request):
        return HttpResponse(status=401)

    topic = request.GET.get("type", "")
    if topic and topic not in ("payment",):
        return HttpResponse(status=200)

    mp_payment_id = request.GET.get("data.id")
    if mp_payment_id:
        mercadopago_service.confirmar_pago_desde_mp(mp_payment_id)

    return HttpResponse(status=200)
