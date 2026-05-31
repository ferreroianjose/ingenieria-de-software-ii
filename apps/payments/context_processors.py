from apps.payments.creditos import creditos_disponibles_count, creditos_resumen_disciplina


def cliente_creditos(request):
    """Créditos disponibles en vistas del flujo cliente."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    path = request.path
    en_flujo_cliente = (
        path.startswith("/classes/actividades")
        or path.startswith("/classes/clase/")
        or path.startswith("/classes/mis-reservas")
        or path.startswith("/payments/inscripcion/")
        or path.startswith("/payments/clase/")
    )
    if not en_flujo_cliente:
        return {}
    return {
        "creditos_disponibles": creditos_disponibles_count(request.user),
        "creditos_por_disciplina": creditos_resumen_disciplina(request.user),
    }
