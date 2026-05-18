from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from GYMFlow.access import staff_required


@login_required
def generate_qr(request):
    """Retorna el fragmento del código QR para el modal."""
    # TODO: Reemplazar con la generación real del QR
    return render(request, "partials/dashboards/_qr_code.html", {"class": "size-full"})


def _staff_section(request, *, page_title, page_subtitle, placeholder_message):
    return render(
        request,
        "staff/section.html",
        {
            "page_title": page_title,
            "page_subtitle": page_subtitle,
            "placeholder_message": placeholder_message,
        },
    )


@staff_required
def staff_asistencia(request):
    return render(
        request,
        "attendance/manage.html",
        {
            "page_title": "Asistencia",
            "page_subtitle": "Pasá asistencia manual cuando falle el código QR.",
            "placeholder_message": "Próximamente: registro manual de asistencia.",
        },
    )

