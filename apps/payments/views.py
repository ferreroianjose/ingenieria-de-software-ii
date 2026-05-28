from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from GYMFlow.access import staff_required
from django.conf import settings
import os

import mercadopago

from apps.classes.models import Inscripcion


@staff_required
def staff_pagos(request):
    return render(request, "payments/manage.html")


@login_required
def pagar_inscripcion(request, inscripcion_id):
    # Allow GET as well so callers can redirect after reserving
    inscripcion = get_object_or_404(Inscripcion, id=inscripcion_id, usuario=request.user)

    # Monto a pagar (usar setting por defecto si no hay tarifa por disciplina)
    amount = getattr(settings, "CLASE_DEFAULT_PRICE", 2500.0)

    sdk = mercadopago.SDK(os.environ.get("MERCADO_PAGO_ACCESS_TOKEN", ""))

    preference_data = {
        "items": [
            {
                "title": f"Clase {inscripcion.clase.disciplina}",
                "quantity": 1,
                "unit_price": float(amount),
            }
        ],
        "payer": {"email": request.user.email},
        "back_urls": {
            "success": request.build_absolute_uri(
                reverse("payments:success", args=[inscripcion.id])
            ),
            "failure": request.build_absolute_uri(
                reverse("payments:failure", args=[inscripcion.id])
            ),
            "pending": request.build_absolute_uri(
                reverse("payments:failure", args=[inscripcion.id])
            ),
        },
        "auto_return": "approved",
    }

    try:
        preference = sdk.preference().create(preference_data)
    except Exception:
        messages.error(request, "Pago fallido por error al intentar conectar al servidor")
        return redirect("classes:mis_reservas")

    response = preference.get("response", {})
    init_point = response.get("sandbox_init_point") or response.get("init_point")
    if not init_point:
        messages.error(request, "Pago fallido por error al intentar conectar al servidor")
        return redirect("classes:mis_reservas")

    # Marcar la inscripción como pendiente de pago si corresponde
    if inscripcion.estado != Inscripcion.ESTADO_PENDIENTE_PAGO:
        inscripcion.estado = Inscripcion.ESTADO_PENDIENTE_PAGO
        inscripcion.save()

    return redirect(init_point)


@login_required
def success(request, inscripcion_id):
    inscripcion = get_object_or_404(Inscripcion, id=inscripcion_id, usuario=request.user)

    # MercadoPago redirige con parámetros como collection_id y collection_status
    collection_status = (
        request.GET.get("collection_status")
        or request.GET.get("status")
        or request.GET.get("collection_status")
    )

    if collection_status and collection_status.lower() == "approved":
        inscripcion.estado = Inscripcion.ESTADO_RESERVADA
        inscripcion.save()
        messages.success(request, "Pago exitoso")
    else:
        messages.error(request, "Pago Fallido por falta de fondos en su cuenta")

    return redirect("classes:mis_reservas")


@login_required
def failure(request, inscripcion_id):
    # Mostrar mensaje genérico de falla y regresar al listado de pagos
    messages.error(request, "Pago Fallido por falta de fondos en su cuenta")
    return redirect("classes:mis_reservas")

