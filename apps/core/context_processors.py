from apps.core.page_chrome import PAGE_CHROME_ADMIN, PAGE_CHROME_DARK
import django.core.signing as signing


def page_chrome(request):
    user = getattr(request, "user", None)
    context = {}
    if user and user.is_authenticated:
        if user.rol in ("ADMIN", "EMPLEADO"):
            context.update(PAGE_CHROME_ADMIN)
        else:
            context.update(PAGE_CHROME_DARK)
            # Generate secure dynamic QR token for CLIENTE
            signer = signing.TimestampSigner()
            token = signer.sign(str(user.id))
            context["qr_url"] = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={token}"
            context["qr_token"] = token
    else:
        context.update(PAGE_CHROME_DARK)
    return context
