import logging
import os
from urllib.parse import urlparse

import mercadopago
from django.conf import settings
from django.urls import reverse

from apps.payments.inscripcion_pago import aplicar_pago_aprobado
from apps.payments.models import Pago

logger = logging.getLogger(__name__)


class ConfirmacionMP:
    APPROVED = "approved"
    ALREADY_COMPLETED = "already_completed"
    PENDING = "pending"
    REJECTED = "rejected"
    MISMATCH = "mismatch"
    ERROR = "error"


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
            preference_data["auto_return"] = (
                "approved"  # vuelta automática si success es HTTPS público
            )

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

    def _fetch_mp_payment(self, mp_payment_id):
        try:
            result = self.sdk.payment().get(mp_payment_id)
        except Exception:
            logger.exception("Error al obtener pago %s de MP", mp_payment_id)
            return None

        if result.get("status") not in (200, 201):
            return None

        return result.get("response") or {}

    def _confirmar_pago_local(self, mp_payment, pago_id):
        """Aplica reglas de negocio según el pago devuelto por la API de MP."""
        ref = mp_payment.get("external_reference")
        try:
            ref_id = int(ref) if ref is not None else None
        except TypeError, ValueError:
            ref_id = None

        if ref_id != pago_id:
            return ConfirmacionMP.MISMATCH

        pago = Pago.objects.filter(id=pago_id).first()
        if not pago:
            return ConfirmacionMP.ERROR

        if pago.estado == Pago.Estado.COMPLETADO:
            return ConfirmacionMP.ALREADY_COMPLETED

        status = (mp_payment.get("status") or "").lower()
        if status == "approved":
            aplicar_pago_aprobado(pago)
            return ConfirmacionMP.APPROVED

        if status in ("pending", "in_process", "in_mediation"):
            return ConfirmacionMP.PENDING

        return ConfirmacionMP.REJECTED

    def confirmar_pago_desde_mp(self, mp_payment_id, pago_id=None):
        """GET /v1/payments/{id}. pago_id desde la URL (redirect) o external_reference (webhook)."""
        mp_payment = self._fetch_mp_payment(mp_payment_id)
        if not mp_payment:
            return ConfirmacionMP.ERROR

        if pago_id is None:
            ref = mp_payment.get("external_reference")
            try:
                pago_id = int(ref)
            except TypeError, ValueError:
                return ConfirmacionMP.ERROR

        return self._confirmar_pago_local(mp_payment, pago_id)


mercadopago_service = MercadoPagoService()
