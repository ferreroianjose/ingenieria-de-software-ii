import logging
import os
from urllib.parse import urlparse

import mercadopago
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)


def _supports_auto_return(success_url):
    """MP exige HTTPS público para auto_return; localhost devuelve 400."""
    parsed = urlparse(success_url)
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    return host not in {"localhost", "127.0.0.1", "0.0.0.0"}


class MercadoPagoService:
    def __init__(self):
        access_token = os.environ.get("MERCADO_PAGO_ACCESS_TOKEN", "")
        self.sdk = mercadopago.SDK(access_token)

    def create_preference(self, pago, request):
        """
        Creates a MercadoPago preference for a given Pago record.
        Returns the init_point URL to redirect the user to.

        En el ecosistema Mercado Pago, una preferencia de pago es un objeto que representa el producto o servicio. Al crear una preferencia de pago, posibilita definirel precio, la cantidad y los medios de pago, así como otras configuraciones relacionadas para el flujo de pago.
        """
        detalles = pago.detalles.select_related(
            "inscripcion__clase__disciplina",
        )
        if not detalles.exists():
            raise ValueError("El pago no tiene inscripciones asociadas.")

        items = []
        for detalle in detalles:
            clase = detalle.inscripcion.clase
            items.append(
                {
                    "title": (
                        f"GYMFLOW: {clase.disciplina.nombre} - "
                        f"{clase.get_dia_semana_display()} {clase.hora_inicio}"
                    ),
                    "quantity": 1,
                    "unit_price": float(detalle.monto_aplicado),
                    "currency_id": "ARS",
                }
            )

        success_url = request.build_absolute_uri(
            reverse("payments:success", args=[pago.id])
        )
        preference_data = {
            "items": items,
            "payer": {"email": pago.usuario.email},
            "back_urls": {
                "success": success_url,
                "failure": request.build_absolute_uri(
                    reverse("payments:failure", args=[pago.id])
                ),
                "pending": request.build_absolute_uri(
                    reverse("payments:failure", args=[pago.id])
                ),
            },
            "external_reference": str(pago.id),
        }

        if _supports_auto_return(success_url):
            preference_data["auto_return"] = "approved"

        try:
            preference = self.sdk.preference().create(preference_data)
        except Exception as e:
            logger.exception("MercadoPago API error: %s", e)
            return None

        if preference.get("status") not in (200, 201):
            message = preference.get("response", {}).get("message", preference)
            logger.error("MercadoPago preference rejected: %s", message)
            return None

        response = preference.get("response", {})
        # Con credenciales de prueba MP devuelve init_point (prod) y sandbox_init_point.
        # Las tarjetas APRO del panel solo funcionan en sandbox.mercadopago.com.ar.
        sandbox_init_point = response.get("sandbox_init_point")
        if settings.DEBUG and sandbox_init_point:
            return sandbox_init_point
        return response.get("init_point")


mercadopago_service = MercadoPagoService()
