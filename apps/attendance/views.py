from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def generate_qr(request):
    """Retorna el fragmento del código QR para el modal."""
    # TODO: Reemplazar con la generación real del QR
    return render(request, "partials/dashboards/_qr_code.html", {"class": "size-full"})
