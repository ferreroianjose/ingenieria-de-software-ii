import hashlib
import hmac
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

def verify_mercadopago_webhook(request) -> bool:
    """Comprueba x-signature con MERCADO_PAGO_WEBHOOK_SECRET (doc MP Webhooks)."""
    secret = getattr(settings, "MERCADO_PAGO_WEBHOOK_SECRET", "").strip()
    if not secret:
        if settings.DEBUG:
            logger.warning("MERCADO_PAGO_WEBHOOK_SECRET vacío; webhook sin verificar.")
            return True
        logger.error("MERCADO_PAGO_WEBHOOK_SECRET requerido.")
        return False

    x_signature = request.headers.get("x-signature") or request.headers.get("X-Signature")
    if not x_signature:
        return False

    x_request_id = request.headers.get("x-request-id") or request.headers.get(
        "X-Request-Id", ""
    )

    data_id = request.GET.get("data.id", "")
    if data_id and not data_id.isdigit():
        data_id = data_id.lower()  # MP: ids alfanuméricos en minúsculas en la firma

    ts = None
    received_hash = None
    for part in x_signature.split(","):
        key, _, value = part.partition("=")
        if key.strip() == "ts":
            ts = value.strip()
        elif key.strip() == "v1":
            received_hash = value.strip()

    if not ts or not received_hash:
        return False

    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"  # template oficial MP
    computed = hmac.new(
        secret.encode(),
        manifest.encode(),
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, received_hash)
