from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.core.page_chrome import (
    PAGE_CHROME_DASHBOARD_CLIENTE,
    PAGE_CHROME_LIGHT,
    PAGE_CHROME_DARK,
    merge_page_chrome,
)
from apps.classes.models import Disciplina, Inscripcion
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
    from apps.classes.ocurrencias import proximas_ocurrencias_dashboard

    ahora = timezone.now()
    proximas = []

    for ocurrencia in proximas_ocurrencias_dashboard(user, limite=limite):
        inscripcion = ocurrencia.inscripcion
        clase = inscripcion.clase
        disciplina = getattr(clase, "disciplina", None)
        if not disciplina:
            continue

        proxima_local = timezone.localtime(ocurrencia.fecha_clase)
        if ocurrencia.fecha_clase < ahora:
            continue

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
    return [
        {k: v for k, v in item.items() if k != "_sort_key"}
        for item in proximas[:limite]
    ]


def _item_membresia_dashboard(inscripcion, *, hoy, vigente, periodo_anterior):
    clase = inscripcion.clase
    disciplina = getattr(clase, "disciplina", None)
    periodo = inscripcion.periodo
    if not disciplina or not periodo:
        return None

    is_pending = inscripcion.estado == "PENDIENTE_PAGO"

    url = reverse("classes:detalle", args=[clase.id])

    if periodo.fecha_inicio_periodo > hoy:
        return {
            "label": disciplina.nombre,
            "subtitle": periodo.nombre,
            "is_future": True,
            "is_pending": is_pending,
            "detail_url": url,
        }

    if vigente and periodo.id == vigente.id:
        return {
            "label": disciplina.nombre,
            "subtitle": f"Este mes · {periodo.nombre}",
            "is_future": False,
            "is_pending": is_pending,
            "detail_url": url,
        }

    if periodo_anterior and periodo.id == periodo_anterior.id:
        return {
            "label": disciplina.nombre,
            "subtitle": f"Mes anterior · {periodo.nombre}",
            "is_future": False,
            "is_pending": is_pending,
            "detail_url": url,
        }

    return {
        "label": disciplina.nombre,
        "subtitle": periodo.nombre,
        "is_future": False,
        "is_pending": is_pending,
        "detail_url": url,
    }


def _titulo_membresia_dashboard(items):
    activas = sum(1 for item in items if not item["is_future"])
    proximas = sum(1 for item in items if item["is_future"])
    
    if activas and proximas:
        return f"{activas} este mes · {proximas} el próximo"
    if proximas:
        return f"{proximas} disciplina{'s' if proximas != 1 else ''} el próximo mes"
    if activas:
        return f"{activas} disciplina{'s' if activas != 1 else ''} este mes"
    return "Tus clases mensuales"


def _estado_cliente_para_dashboard(user):
    from apps.payments.models import Pago
    from apps.classes.models import Inscripcion

    pagos_pendientes_sueltas = Pago.objects.filter(
        usuario=user,
        estado=Pago.Estado.PENDIENTE,
        detalles__inscripcion__tipo=Inscripcion.Tipo.CLASE_SUELTA
    ).distinct().count()

    hoy = timezone.localdate()
    vigente = periodo_vigente(hoy)
    if not vigente:
        return {
            "show_membership_status": False,
            "membership_status_label": "",
            "membership_status_hint": "",
            "membership_items": [],
            "membership_pending_payments": 0,
            "agenda_pending_payments": pagos_pendientes_sueltas,
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
            PeriodoCobro.objects.filter(
                fecha_fin_periodo__lt=vigente.fecha_inicio_periodo
            )
            .order_by("-fecha_fin_periodo")
            .first()
        )
    tiene_anterior_valido = bool(
        periodo_anterior
        and inscripciones_mensuales.filter(periodo=periodo_anterior).exists()
    )
    tiene_futuro = inscripciones_mensuales.filter(
        periodo__fecha_inicio_periodo__gt=hoy
    ).exists()
    es_abonado = tiene_vigente or tiene_anterior_valido or tiene_futuro
    if not es_abonado:
        return {
            "show_membership_status": False,
            "membership_status_label": "",
            "membership_items": [],
            "membership_pending_payments": 0,
            "agenda_pending_payments": pagos_pendientes_sueltas,
        }

    periodos_visibles = {vigente.id}
    if tiene_anterior_valido and periodo_anterior:
        periodos_visibles.add(periodo_anterior.id)
    periodos_visibles.update(
        inscripciones_mensuales.filter(
            periodo__fecha_inicio_periodo__gt=hoy
        ).values_list("periodo_id", flat=True)
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

    pagos_pendientes_mensual = Pago.objects.filter(
        usuario=user,
        estado=Pago.Estado.PENDIENTE,
        detalles__inscripcion__tipo=Inscripcion.Tipo.MENSUAL
    ).distinct().count()

    tiene_proximo = any(item["is_future"] for item in items)
    tiene_activo = any(not item["is_future"] for item in items)

    return {
        "show_membership_status": True,
        "membership_status_label": _titulo_membresia_dashboard(items),
        "membership_items": items,
        "membership_pending_payments": pagos_pendientes_mensual,
        "agenda_pending_payments": pagos_pendientes_sueltas,
    }


def _cartelera_para_dashboard(limite=5):
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
                else disciplina.descripcion
                or "Mirá horarios y elegí la clase que mejor te quede."
            ),
            "badge": f"{disciplina.clases_disponibles} horario{'s' if disciplina.clases_disponibles != 1 else ''}",
            "url": reverse("classes:cronograma", args=[disciplina.pk]),
        }
        for disciplina in disciplinas
    ]


def _disciplinas_de_pago(pago):
    nombres = []
    vistos = set()
    for detalle in pago.detalles.all():
        nombre = detalle.inscripcion.clase.disciplina.nombre
        if nombre not in vistos:
            vistos.add(nombre)
            nombres.append(nombre)
    return ", ".join(nombres)


def _historial_pagos_para_dashboard(user, limite=2):
    pagos = (
        Pago.objects.filter(usuario=user, estado=Pago.Estado.COMPLETADO)
        .select_related("periodo")
        .prefetch_related("detalles__inscripcion__clase__disciplina")
        .order_by("-fecha_pago")[:limite]
    )
    return [
        {
            "disciplina": _disciplinas_de_pago(pago) or "Pago acreditado",
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
        return render(
            request,
            "dashboards/admin.html",
            {"page_section": "Panel de administración"},
        )

    if user.rol == "EMPLEADO":
        return render(
            request,
            "dashboards/empleado.html",
            {"page_section": "Panel de empleado"},
        )

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
            "membership_items": estado["membership_items"],
            "membership_pending_payments": estado["membership_pending_payments"],
            "agenda_pending_payments": estado.get("agenda_pending_payments", 0),
            "show_membership_status": estado["show_membership_status"],
            "activities_url": reverse("classes:actividades"),
            "my_reservations_url": reverse("classes:mis_reservas"),
            "faq_url": reverse("faq"),
            "missing_emergency_phone": not bool(
                user.telefono_emergencia and user.telefono_emergencia.strip()
            ),
            "settings_url": reverse("settings"),
        },
    )


@login_required
def faq(request):
    return render(
        request,
        "support/faq.html",
        merge_page_chrome(
            PAGE_CHROME_LIGHT,
            page_section="Preguntas frecuentes",
        ),
    )
