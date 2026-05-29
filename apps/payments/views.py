from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from GYMFlow.access import staff_required
from django.conf import settings
from decimal import Decimal

from apps.classes.models import Inscripcion
from apps.payments.models import Pago, PagoInscripcion, PrecioDisciplina
from apps.payments.services import aplicar_pago_aprobado, mercadopago_service
from apps.payments.webhook_verify import verify_mercadopago_webhook


@staff_required
def staff_pagos(request):
    return render(request, "payments/manage.html")


@login_required
def pagar_inscripcion(request, inscripcion_id):
    # Allow GET as well so callers can redirect after reserving
    inscripcion = get_object_or_404(Inscripcion, id=inscripcion_id, usuario=request.user)

    # Determinar el costo según Periodo y Disciplina
    try:
        precio_disciplina = PrecioDisciplina.objects.get(
            disciplina=inscripcion.clase.disciplina,
            periodo=inscripcion.periodo
        )
        base_amount = precio_disciplina.monto
    except PrecioDisciplina.DoesNotExist:
        # #TODO: Esto debería ser un ERROR, no un valor por defecto
        base_amount = Decimal(getattr(settings, "CLASE_DEFAULT_PRICE", "2500.0"))

    amount_to_pay = base_amount

    # No abonados: seña -> 50% o total -> 100%
    modalidad_solicitada = request.GET.get('modalidad', 'TOTAL').upper()
    if inscripcion.tipo == Inscripcion.Tipo.CLASE_SUELTA and modalidad_solicitada == 'SENA':
        amount_to_pay = base_amount / Decimal('2.0')

    # Crear pago en estado pendiente
    pago = Pago.objects.create(
        usuario=request.user,
        periodo=inscripcion.periodo,
        monto=amount_to_pay,
        metodo=Pago.Metodo.MERCADOPAGO,
        estado=Pago.Estado.PENDIENTE
    )

    # Crea el registro en la tabla intermedia
    PagoInscripcion.objects.create(
        pago=pago,
        inscripcion=inscripcion,
        monto_aplicado=amount_to_pay
    )

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


@login_required
def success(request, pago_id):
    pago = get_object_or_404(Pago, id=pago_id, usuario=request.user)

    # Vuelta del checkout en el navegador; el webhook confirma por servidor si no llega acá.
    collection_status = (
        request.GET.get("status")
        or request.GET.get("collection_status")
    )

    if collection_status and collection_status.lower() == "approved":
        aplicar_pago_aprobado(pago)
        messages.success(request, "Pago exitoso")
    else:
        messages.error(request, "El pago no pudo ser completado.")

    return redirect("classes:mis_reservas")


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
        mercadopago_service.sync_pago_from_mp_payment_id(mp_payment_id)

    return HttpResponse(status=200)  # MP reintenta si no es 2xx


@login_required
def failure(request, pago_id):
    pago = get_object_or_404(Pago, id=pago_id, usuario=request.user)
    pago.estado = Pago.Estado.FALLIDO
    pago.save()
    messages.error(request, "Pago fallido. Por favor intente nuevamente.")
    return redirect("classes:mis_reservas")
