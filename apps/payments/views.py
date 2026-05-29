from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from GYMFlow.access import staff_required

from apps.classes.models import Inscripcion
from apps.payments.inscripcion_pago import monto_a_cobrar, preparar_pago_mercadopago
from apps.payments.models import Pago, PagoInscripcion
from apps.payments.services import ConfirmacionMP, mercadopago_service
from apps.payments.webhook_verify import verify_mercadopago_webhook


@staff_required
def staff_pagos(request):
    return render(request, "payments/manage.html")


@login_required
def pagar_inscripcion(request, inscripcion_id):
    inscripcion = get_object_or_404(Inscripcion, id=inscripcion_id, usuario=request.user)

    if inscripcion.estado == Inscripcion.Estado.RESERVADA:
        messages.info(request, "Esta clase ya está reservada.")
        return redirect("classes:mis_reservas")

    modalidad = request.GET.get("modalidad", "TOTAL").upper()
    try:
        amount_to_pay = monto_a_cobrar(inscripcion, modalidad)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("classes:mis_reservas")

    if amount_to_pay <= 0:
        messages.info(request, "Esta inscripción ya está paga.")
        return redirect("classes:mis_reservas")

    pago = preparar_pago_mercadopago(inscripcion, request.user, amount_to_pay)

    # Redirige al usuario a la página de MercadoPago para completar el pago
    init_point = mercadopago_service.create_preference(pago, request)

    # #TODO: ESTO NO DEBERÍA ESTAR EN EL MÓDULO DE PAGOS, SINO EN EL DE INSCRIPCIONES.
    if inscripcion.estado != Inscripcion.Estado.PENDIENTE_PAGO:
        inscripcion.estado = Inscripcion.Estado.PENDIENTE_PAGO
        inscripcion.save()

    if not init_point:
        messages.error(request, "Pago fallido por error al intentar conectar al servidor")
        return redirect("classes:mis_reservas")

    return redirect(init_point)


def _mp_payment_id_from_request(request):
    return request.GET.get("payment_id") or request.GET.get("collection_id")


def _retorno_checkout(request, pago_id, *, marcar_fallido_si_rechazado):
    # MP exige back_urls distintas (success/failure/pending), pero el estado real
    # sale siempre de consultar la API de MP por el id de pago.
    # success y failure son alias: misma consulta; solo cambia el mensaje si no
    # viene el id de pago y si marcamos FALLIDO al rechazar desde la URL de failure.
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


# MP notifica por servidor (no es el redirect del usuario).
@csrf_exempt
@require_POST
def mercadopago_webhook(request):
    if not verify_mercadopago_webhook(request):
        return HttpResponse(status=401)

    topic = request.GET.get("type", "")
    if topic and topic not in ("payment",):
        return HttpResponse(status=200)

    # El estado se consulta en la API de MP, por seguridad
    mp_payment_id = request.GET.get("data.id")
    if mp_payment_id:
        mercadopago_service.confirmar_pago_desde_mp(mp_payment_id)

    return HttpResponse(status=200)  # MP reintenta si no es 2xx
