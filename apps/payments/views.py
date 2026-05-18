from django.shortcuts import render
from GYMFlow.access import staff_required


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
def staff_pagos(request):
    return render(
        request,
        "payments/manage.html",
        {
            "page_title": "Pagos",
            "page_subtitle": "Registrá cobros en efectivo o presenciales en sucursal.",
            "placeholder_message": "Próximamente: registro de pagos en sucursal.",
        },
    )

