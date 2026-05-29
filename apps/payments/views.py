from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from GYMFlow.access import staff_required

from apps.classes import services as class_services
from apps.classes.exceptions import InscripcionDuplicada, ReservaError
from apps.classes.models import Class, Inscripcion
from apps.payments.inscripcion_pago import (
    fecha_clase_desde_intencion,
    intencion_pago_para_clase,
    limpiar_intencion_pago,
    monto_a_cobrar,
    opciones_pago_inscripcion,
    opciones_pago_para_clase,
    preparar_pago_mercadopago,
    resumen_abono_para_clase,
    resumen_abono_para_inscripcion,
)
from apps.payments.models import Pago, PeriodoCobro
from apps.payments.services import ConfirmacionMP, mercadopago_service
from apps.payments.webhook_verify import verify_mercadopago_webhook


@staff_required
def staff_pagos(request):
    return render(request, "payments/manage.html")


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
):
    return {
        "clase": clase,
        "periodo": periodo,
        "fecha_clase": fecha_clase,
        "es_inscripcion_mensual": tipo == Inscripcion.Tipo.MENSUAL,
        "opciones": opciones,
        "abono_resumen": abono_resumen,
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

    opciones = opciones_pago_para_clase(clase, periodo, tipo)
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
        ),
    )


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
        amount_to_pay = monto_a_cobrar(inscripcion, modalidad)
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

    if amount_to_pay <= 0:
        if tipo == Inscripcion.Tipo.MENSUAL:
            messages.error(
                request, "No quedan clases de este horario en el mes elegido."
            )
        else:
            messages.info(request, "No hay monto pendiente de pago.")
        limpiar_intencion_pago(request)
        return redirect("classes:detalle", clase_id=clase_id)

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
    opciones = opciones_pago_inscripcion(inscripcion)
    if abono_resumen is None and not opciones:
        if inscripcion.tipo == Inscripcion.Tipo.MENSUAL:
            messages.error(
                request, "No quedan clases de este horario en el mes elegido."
            )
            return redirect("classes:detalle", clase_id=inscripcion.clase_id)
        messages.info(request, "Esta inscripción ya está paga.")
        return redirect("classes:mis_reservas")

    pagar_url = reverse("payments:pagar", args=[inscripcion.id])
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
    try:
        amount_to_pay = monto_a_cobrar(inscripcion, modalidad)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("payments:seleccion_pago", inscripcion_id=inscripcion_id)

    if amount_to_pay <= 0:
        messages.info(request, "Esta inscripción ya está paga.")
        return redirect("classes:mis_reservas")

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
