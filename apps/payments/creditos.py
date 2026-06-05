"""Consultas y uso de créditos por cancelación anticipada."""

from decimal import Decimal

from django.db import transaction

from apps.payments.models import Credito


def creditos_disponibles_count(usuario, periodo=None):
    """Créditos DISPONIBLE del usuario (todos los períodos si periodo es None)."""
    qs = Credito.objects.filter(
        usuario=usuario,
        estado=Credito.Estado.DISPONIBLE,
    )
    if periodo is not None:
        qs = qs.filter(periodo=periodo)
    return qs.count()


def creditos_resumen_disciplina(usuario):
    """Créditos disponibles agrupados por disciplina y período."""
    from django.db.models import Count

    rows = (
        Credito.objects.filter(usuario=usuario, estado=Credito.Estado.DISPONIBLE)
        .values("disciplina__nombre", "periodo__nombre")
        .annotate(cantidad=Count("id"))
        .order_by("-periodo__fecha_inicio_periodo", "disciplina__nombre")
    )
    return [
        {
            "disciplina": row["disciplina__nombre"],
            "periodo": row["periodo__nombre"],
            "cantidad": row["cantidad"],
        }
        for row in rows
    ]


def tiene_credito_disponible(usuario, periodo, disciplina):
    return Credito.objects.filter(
        usuario=usuario,
        periodo=periodo,
        disciplina=disciplina,
        estado=Credito.Estado.DISPONIBLE,
    ).exists()


def creditos_disponibles_por_disciplina(usuario, periodo, disciplina):
    """Cantidad de créditos disponibles para una disciplina y período concretos."""
    return Credito.objects.filter(
        usuario=usuario,
        periodo=periodo,
        disciplina=disciplina,
        estado=Credito.Estado.DISPONIBLE,
    ).count()


def valor_credito_disponible(usuario, periodo, disciplina):
    """Monto que cubre un crédito disponible (precio unitario de la disciplina)."""
    from apps.payments.inscripcion_pago import precio_disciplina_periodo

    if not tiene_credito_disponible(usuario, periodo, disciplina):
        return Decimal("0")
    return precio_disciplina_periodo(disciplina, periodo)


def consumir_credito(usuario, periodo, disciplina):
    from apps.classes.exceptions import ReservaError

    with transaction.atomic():
        credito = (
            Credito.objects.select_for_update()
            .filter(
                usuario=usuario,
                periodo=periodo,
                disciplina=disciplina,
                estado=Credito.Estado.DISPONIBLE,
            )
            .order_by("pk")
            .first()
        )
        if not credito:
            raise ReservaError(
                "No tenés créditos disponibles para esta disciplina en el período."
            )
        credito.estado = Credito.Estado.UTILIZADO
        credito.save(update_fields=["estado"])
        return credito
