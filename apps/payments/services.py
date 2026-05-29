import logging
import os
from decimal import Decimal
from urllib.parse import urlparse

import mercadopago
from django.conf import settings
from django.urls import reverse

from apps.classes.models import Inscripcion
from apps.payments.models import Pago, PrecioDisciplina

logger = logging.getLogger(__name__)


def aplicar_pago_aprobado(pago):
    """Marca Pago completado y la inscripción RESERVADA (o sigue pendiente si fue seña)."""
    pago.estado = Pago.Estado.COMPLETADO
    pago.save(update_fields=["estado"])

    for detalle in pago.detalles.select_related("inscripcion"):
        inscripcion = detalle.inscripcion
        try:
            base_amount = PrecioDisciplina.objects.get(
                disciplina=inscripcion.clase.disciplina,
                periodo=inscripcion.periodo,
            ).monto
        except PrecioDisciplina.DoesNotExist:
            base_amount = Decimal(getattr(settings, "CLASE_DEFAULT_PRICE", "2500.0"))

        # Seña (50%): el cupo queda asegurado pero falta el resto.
        if (
            inscripcion.tipo == Inscripcion.Tipo.CLASE_SUELTA
            and pago.monto < base_amount
        ):
            inscripcion.estado = Inscripcion.Estado.PENDIENTE_PAGO
        else:
            inscripcion.estado = Inscripcion.Estado.RESERVADA
        inscripcion.save(update_fields=["estado"])


def _supports_auto_return(success_url):
    """MP exige HTTPS público para auto_return; localhost devuelve 400."""
    parsed = urlparse(success_url)
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    return host not in {"localhost", "127.0.0.1", "0.0.0.0"}


def _absolute_url(request, view_name, *args, **kwargs):
    """HTTPS público vía PUBLIC_WEBHOOK_BASE_URL; si no, la URL del request."""
    path = reverse(view_name, args=args, kwargs=kwargs)
    public_base = getattr(settings, "PUBLIC_WEBHOOK_BASE_URL", "").strip().rstrip("/")
    if public_base.startswith("https://"):
        return f"{public_base}{path}"
    return request.build_absolute_uri(path)


class MercadoPagoService:
    """Checkout Pro: preferencia de cobro y consulta de pagos vía API."""

    def __init__(self):
        access_token = os.environ.get("MERCADO_PAGO_ACCESS_TOKEN", "")
        self.sdk = mercadopago.SDK(access_token)

    def create_preference(self, pago, request):
        """Crea la preferencia en MP y devuelve la URL del checkout (init_point)."""
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

        success_url = _absolute_url(request, "payments:success", pago.id)
        preference_data = {
            "items": items,
            "payer": {"email": pago.usuario.email},
            # Redirect del navegador tras pagar (complementa al webhook).
            "back_urls": {
                "success": success_url,
                "failure": _absolute_url(request, "payments:failure", pago.id),
                "pending": _absolute_url(request, "payments:failure", pago.id),
            },
            "external_reference": str(pago.id),
        }

        if _supports_auto_return(success_url):
            preference_data["auto_return"] = "approved"  # vuelta automática si success es HTTPS público

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
        # Credenciales de prueba: tarjetas APRO solo en sandbox.mercadopago.com.ar
        if settings.DEBUG:
            return response.get("sandbox_init_point")
        return response.get("init_point")

    def sync_pago_from_mp_payment_id(self, mp_payment_id):
        """Webhook: id de MP → GET payment → external_reference → aplicar si approved."""
        try:
            result = self.sdk.payment().get(mp_payment_id)
        except Exception:
            logger.exception("Error al obtener pago %s de MP", mp_payment_id)
            return False

        if result.get("status") not in (200, 201):
            return False

        mp_payment = result.get("response") or {}
        if mp_payment.get("status") != "approved":
            return False  # pending/rejected: no tocamos el Pago local

        ref = mp_payment.get("external_reference")  # = str(pago.id) al crear la preferencia
        if not ref:
            return False

        try:
            pago_id = int(ref)
        except TypeError, ValueError:
            return False

        pago = Pago.objects.filter(id=pago_id).first()
        if not pago or pago.estado == Pago.Estado.COMPLETADO:
            return bool(pago)  # idempotente si el webhook se reenvía

        aplicar_pago_aprobado(pago)
        return True


mercadopago_service = MercadoPagoService()
