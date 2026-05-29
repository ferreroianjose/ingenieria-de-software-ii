from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from GYMFlow.page_chrome import (
    PAGE_CHROME_DASHBOARD_CLIENTE,
    PAGE_CHROME_LIGHT,
    merge_page_chrome,
)
from apps.classes.models import Disciplina, Inscripcion
from apps.classes.services import proxima_ocurrencia
from apps.payments.models import Pago, PeriodoCobro
from apps.payments.periodos import periodo_vigente


MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
WEEKDAYS_ES = (
    "Lunes",
    "Martes",
    "Miércoles",
    "Jueves",
    "Viernes",
    "Sábado",
    "Domingo",
)


def _mes_ano_es(fecha):
    return f"{MONTHS_ES[fecha.month - 1].capitalize()} {fecha.year}"


def _monto_ars_legible(monto):
    # Usamos formato AR para mantener consistencia visual en el dashboard.
    entero = int(round(float(monto)))
    return f"${entero:,}".replace(",", ".")


def _proximas_clases_para_dashboard(user, limite=4):
    ahora = timezone.now()
    proximas = []
    vistos = set()
    inscripciones_qs = (
        Inscripcion.objects.filter(usuario=user)
        .exclude(estado=Inscripcion.Estado.CANCELADA)
        .select_related("clase", "clase__disciplina", "clase__sala", "clase__sala__sede")
        .order_by("fecha_clase", "fecha_inscripcion")
    )

    for inscripcion in inscripciones_qs:
        clase = inscripcion.clase
        disciplina = getattr(clase, "disciplina", None)
        if not disciplina:
            continue

        proxima = inscripcion.fecha_clase or proxima_ocurrencia(clase)
        if not proxima or proxima < ahora:
            continue

        proxima_local = timezone.localtime(proxima)
        clave = (clase.id, proxima_local.isoformat())
        if clave in vistos:
            continue
        vistos.add(clave)

        lugar = "Sala a confirmar"
        if clase.sala_id:
            lugar = clase.sala.nombre
            if getattr(clase.sala, "sede", None):
                lugar = f"{clase.sala.nombre} · {clase.sala.sede.nombre}"

        proximas.append(
            {
                "disciplina": disciplina.nombre,
                "weekday": WEEKDAYS_ES[proxima_local.weekday()],
                "date": proxima_local.strftime("%d/%m"),
                "time": proxima_local.strftime("%H:%M"),
                "location": lugar,
                "status": inscripcion.get_estado_display(),
                "detail_url": reverse("classes:detalle", args=[clase.id]),
                "_sort_key": proxima_local,
            }
        )

    proximas.sort(key=lambda item: item["_sort_key"])
    return [{k: v for k, v in item.items() if k != "_sort_key"} for item in proximas[:limite]]


def _item_membresia_dashboard(inscripcion, *, hoy, vigente, periodo_anterior):
    clase = inscripcion.clase
    disciplina = getattr(clase, "disciplina", None)
    periodo = inscripcion.periodo
    if not disciplina or not periodo:
        return None

    if periodo.fecha_inicio_periodo > hoy:
        return {
            "label": disciplina.nombre,
            "tag": "Próximo",
            "subtitle": periodo.nombre,
            "is_future": True,
        }

    if vigente and periodo.id == vigente.id:
        return {
            "label": disciplina.nombre,
            "tag": "Activo",
            "subtitle": f"Este mes · {periodo.nombre}",
            "is_future": False,
        }

    if periodo_anterior and periodo.id == periodo_anterior.id:
        return {
            "label": disciplina.nombre,
            "tag": "Activo",
            "subtitle": f"Mes anterior · {periodo.nombre}",
            "is_future": False,
        }

    return {
        "label": disciplina.nombre,
        "tag": "Activo",
        "subtitle": periodo.nombre,
        "is_future": False,
    }


def _hint_membresia_dashboard(items):
    activas = sum(1 for item in items if not item["is_future"])
    proximas = sum(1 for item in items if item["is_future"])
    if activas and proximas:
        return (
            f"{activas} disciplina{'s' if activas != 1 else ''} este mes · "
            f"{proximas} confirmada{'s' if proximas != 1 else ''} para el próximo"
        )
    if proximas:
        return (
            f"{proximas} disciplina{'s' if proximas != 1 else ''} "
            f"confirmada{'s' if proximas != 1 else ''} para el próximo mes"
        )
    if activas:
        return f"{activas} disciplina{'s' if activas != 1 else ''} incluidas este mes"
    return "Tus clases mensuales están al día"


def _titulo_membresia_dashboard(*, tiene_activo, tiene_proximo):
    if tiene_activo and tiene_proximo:
        return "Este mes y el próximo"
    if tiene_proximo:
        return "Próximo mes confirmado"
    return "Mes en curso"


def _estado_cliente_para_dashboard(user):
    hoy = timezone.localdate()
    vigente = periodo_vigente(hoy)
    if not vigente:
        return {
            "show_membership_status": False,
            "membership_status_label": "",
            "membership_status_hint": "",
            "membership_items": [],
            "membership_pending_payments": 0,
        }

    inscripciones_mensuales = Inscripcion.objects.filter(
        usuario=user,
        tipo=Inscripcion.Tipo.MENSUAL,
    ).exclude(estado=Inscripcion.Estado.CANCELADA)

    tiene_vigente = inscripciones_mensuales.filter(periodo=vigente).exists()
    considerar_periodo_anterior = hoy < vigente.apertura_general
    periodo_anterior = None
    if considerar_periodo_anterior:
        periodo_anterior = (
            PeriodoCobro.objects.filter(fecha_fin_periodo__lt=vigente.fecha_inicio_periodo)
            .order_by("-fecha_fin_periodo")
            .first()
        )
    tiene_anterior_valido = bool(
        periodo_anterior and inscripciones_mensuales.filter(periodo=periodo_anterior).exists()
    )
    tiene_futuro = inscripciones_mensuales.filter(periodo__fecha_inicio_periodo__gt=hoy).exists()
    es_abonado = tiene_vigente or tiene_anterior_valido or tiene_futuro
    if not es_abonado:
        return {
            "show_membership_status": False,
            "membership_status_label": "",
            "membership_status_hint": "",
            "membership_items": [],
            "membership_pending_payments": 0,
        }

    periodos_visibles = {vigente.id}
    if tiene_anterior_valido and periodo_anterior:
        periodos_visibles.add(periodo_anterior.id)
    periodos_visibles.update(
        inscripciones_mensuales.filter(periodo__fecha_inicio_periodo__gt=hoy).values_list(
            "periodo_id", flat=True
        )
    )

    inscripciones = (
        inscripciones_mensuales.filter(periodo_id__in=periodos_visibles)
        .select_related("clase__disciplina", "periodo")
        .order_by("periodo__fecha_inicio_periodo", "clase__disciplina__nombre")
    )

    items = []
    vistos = set()
    for inscripcion in inscripciones:
        disciplina = getattr(inscripcion.clase, "disciplina", None)
        if not disciplina or not inscripcion.periodo_id:
            continue
        clave = (disciplina.id, inscripcion.periodo_id)
        if clave in vistos:
            continue
        vistos.add(clave)
        item = _item_membresia_dashboard(
            inscripcion,
            hoy=hoy,
            vigente=vigente,
            periodo_anterior=periodo_anterior,
        )
        if item:
            items.append(item)

    pagos_pendientes = Pago.objects.filter(usuario=user, estado=Pago.Estado.PENDIENTE).count()
    tiene_proximo = any(item["is_future"] for item in items)
    tiene_activo = any(not item["is_future"] for item in items)

    return {
        "show_membership_status": True,
        "membership_status_label": _titulo_membresia_dashboard(
            tiene_activo=tiene_activo,
            tiene_proximo=tiene_proximo,
        ),
        "membership_status_hint": _hint_membresia_dashboard(items),
        "membership_items": items,
        "membership_pending_payments": pagos_pendientes,
    }


def _cartelera_para_dashboard(limite=3):
    disciplinas = (
        Disciplina.objects.filter(class__estado="disponible")
        .annotate(
            clases_disponibles=Count(
                "class",
                filter=Q(class__estado="disponible"),
                distinct=True,
            )
        )
        .order_by("-clases_disponibles", "nombre")
        .distinct()[:limite]
    )
    return [
        {
            "title": disciplina.nombre,
            "subtitle": (
                disciplina.descripcion[:110] + "..."
                if disciplina.descripcion and len(disciplina.descripcion) > 110
                else disciplina.descripcion or "Mirá horarios y elegí la clase que mejor te quede."
            ),
            "badge": f"{disciplina.clases_disponibles} horario{'s' if disciplina.clases_disponibles != 1 else ''}",
            "url": reverse("classes:cronograma", args=[disciplina.pk]),
        }
        for disciplina in disciplinas
    ]


def _historial_pagos_para_dashboard(user, limite=4):
    pagos = (
        Pago.objects.filter(usuario=user, estado=Pago.Estado.COMPLETADO)
        .select_related("periodo")
        .order_by("-fecha_pago")[:limite]
    )
    return [
        {
            "month": pago.periodo.nombre if pago.periodo_id else _mes_ano_es(pago.fecha_pago.date()),
            "method": pago.get_metodo_display(),
            "amount": _monto_ars_legible(pago.monto),
        }
        for pago in pagos
    ]


def root(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return redirect("login")


@login_required
def dashboard(request):
    """Página principal después de iniciar sesión."""
    user = request.user

    if user.rol == "ADMIN":
        return render(request, "dashboards/admin.html")

    if user.rol == "EMPLEADO":
        return render(request, "dashboards/empleado.html")

    # Else es un usuario cliente.
    estado = _estado_cliente_para_dashboard(user)
    return render(
        request,
        "dashboards/cliente.html",
        {
            **merge_page_chrome(PAGE_CHROME_DASHBOARD_CLIENTE),
            "next_classes": _proximas_clases_para_dashboard(user),
            "featured_disciplines": _cartelera_para_dashboard(),
            "payment_history": _historial_pagos_para_dashboard(user),
            "membership_status_label": estado["membership_status_label"],
            "membership_status_hint": estado["membership_status_hint"],
            "membership_items": estado["membership_items"],
            "membership_pending_payments": estado["membership_pending_payments"],
            "show_membership_status": estado["show_membership_status"],
            "activities_url": reverse("classes:actividades"),
            "my_reservations_url": reverse("classes:mis_reservas"),
            "faq_url": reverse("faq"),
        },
    )


@login_required
def faq(request):
    return render(request, "support/faq.html", merge_page_chrome(PAGE_CHROME_LIGHT))
