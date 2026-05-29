import os
import mercadopago
from django.conf import settings
from django.urls import reverse

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
                }
            )

        preference_data = {
            "items": items,
            "payer": {"email": pago.usuario.email},
            "back_urls": {
                "success": request.build_absolute_uri(
                    reverse("payments:success", args=[pago.id])
                ),
                "failure": request.build_absolute_uri(
                    reverse("payments:failure", args=[pago.id])
                ),
                "pending": request.build_absolute_uri(
                    reverse("payments:failure", args=[pago.id])
                ),
            },
            "auto_return": "approved",
            "external_reference": str(pago.id), # Links MP a nuestro sistema
        }

        try:
            preference = self.sdk.preference().create(preference_data)
        except Exception as e:
            print(f"MercadoPago API Error: {e}")
            return None

        return preference.get("response", {}).get("init_point")

mercadopago_service = MercadoPagoService()
