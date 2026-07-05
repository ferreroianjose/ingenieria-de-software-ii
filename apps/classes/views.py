from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from apps.core.access import admin_required, staff_required
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.urls import reverse
from django.core.paginator import Paginator

from .forms import ClassForm, TeacherForm, SedeForm, SalaForm, DisciplinaForm
from .models import Class, Teacher, Sede, Sala, Disciplina, Inscripcion
from . import services
from .exceptions import InscripcionDuplicada
from .services import proxima_ocurrencia
from .search import apply_text_search
from .htmx import hx_ok
from . import cliente
from .flow import build_flow_stepper_context

from urllib.parse import urlencode


def _flow_session_urls(request, *, disciplina_id=None):
    saved_disciplina_id = request.session.get("flow_disciplina_id")
    saved_clase_id = request.session.get("flow_clase_id")
    saved_clase_disciplina_id = request.session.get("flow_clase_disciplina_id")
    saved_pago_url = request.session.get("flow_pago_url")

    urls = {}
    if saved_disciplina_id:
        urls["horarios_url"] = reverse("classes:cronograma", args=[saved_disciplina_id])

    class_matches_disciplina = bool(
        saved_clase_id
        and saved_clase_disciplina_id
        and str(saved_clase_disciplina_id) == str(saved_disciplina_id)
    )

    if class_matches_disciplina:
        urls["clase_url"] = reverse("classes:detalle", args=[saved_clase_id])
        urls["pago_url"] = saved_pago_url

    if disciplina_id is not None and str(saved_disciplina_id) != str(disciplina_id):
        urls.pop("clase_url", None)
        urls.pop("pago_url", None)
        urls["horarios_url"] = reverse("classes:cronograma", args=[disciplina_id])

    return urls


def _hx_ok_or_redirect(
    request,
    *,
    message,
    redirect_to,
    level="success",
    close_modal=None,
    refresh=None,
    redirect_url=None,
    locations_reload=None,
    trigger=None,
):
    if request.headers.get("HX-Request"):
        return hx_ok(
            request,
            message=message,
            level=level,
            close_modal=close_modal,
            refresh=refresh,
            redirect_url=redirect_url,
            locations_reload=locations_reload,
            trigger=trigger,
        )
    messages.add_message(
        request, messages.SUCCESS if level == "success" else messages.ERROR, message
    )
    return redirect(redirect_to)


def _class_rows_refresh():
    return {
        "url": reverse("classes:class_rows"),
        "target": "#class-table-panel",
    }


def _disciplina_rows_refresh():
    return {
        "url": reverse("classes:disciplina_rows"),
        "target": "#disciplinas-tbody",
        "searchFormId": "disciplinas-search-form",
    }


def _teacher_rows_refresh():
    return {
        "url": reverse("classes:teacher_rows"),
        "target": "#teachers-tbody",
        "searchFormId": "teachers-search-form",
    }


def _sala_rows_refresh(sede_id):
    return {
        "url": reverse("classes:sala_rows"),
        "target": "#salas-tbody",
        "query": {"sede_id": str(sede_id)},
    }


def _edit_initial_for_class(instance):
    initial = {}
    if instance.sala_id:
        initial["sede"] = instance.sala.sede_id
    if instance.hora_inicio:
        initial["hora"] = instance.hora_inicio.hour
        initial["minuto"] = instance.hora_inicio.minute
    if instance.duracion:
        initial["duracion_minutos"] = instance.duracion_minutos
    return initial


def _render_modal(
    request,
    *,
    body_template,
    form,
    title,
    subtitle,
    button_label,
    action_url,
    show_var,
    container_id,
    variant="center",
    status=200,
    **extra,
):
    return render(
        request,
        "partials/ui/modals/_modal.html",
        {
            "modal_form": form,
            "modal_title": title,
            "modal_subtitle": subtitle,
            "modal_button_label": button_label,
            "action_url": action_url,
            "modal_show_var": show_var,
            "modal_container_id": container_id,
            "modal_variant": variant,
            "modal_body_template": body_template,
            **extra,
        },
        status=status,
    )


def _class_modal_context(form, instance=None):
    editing = instance is not None and instance.pk
    if editing:
        return {
            "body_template": "partials/classes/shared/_class_modal_body.html",
            "form": form,
            "title": "Editar clase",
            "subtitle": "Modificá los datos de la clase y guarda los cambios.",
            "button_label": "Guardar cambios",
            "action_url": reverse("classes:update_class", args=[instance.pk]),
            "show_var": "classDrawerOpen",
            "container_id": "class-drawer",
            "variant": "drawer",
        }
    return {
        "body_template": "partials/classes/shared/_class_modal_body.html",
        "form": form,
        "title": "Nueva clase",
        "subtitle": 'Ingresá los datos de la nueva clase y presiona "Publicar clase" para guardar.',
        "button_label": "Publicar clase",
        "action_url": reverse("classes:create_class"),
        "show_var": "classDrawerOpen",
        "container_id": "class-drawer",
        "variant": "drawer",
    }


def _render_class_drawer(request, form, instance=None, status=200):
    ctx = _class_modal_context(form, instance)
    return render(
        request,
        "partials/classes/list/_class_drawer_panel.html",
        {
            "modal_form": ctx["form"],
            "modal_title": ctx["title"],
            "modal_subtitle": ctx["subtitle"],
            "modal_button_label": ctx["button_label"],
            "action_url": ctx["action_url"],
        },
        status=status,
    )


@staff_required
def class_roster_drawer(request, class_id):
    clase = get_object_or_404(Class.objects.all(), pk=class_id)
    
    from apps.payments.models import PeriodoCobro
    from apps.payments.periodos import periodo_vigente
    
    periodos = PeriodoCobro.objects.order_by("-fecha_inicio_periodo")
    periodo_id = request.GET.get("periodo_id")
    
    if periodo_id == "all":
        inscripciones = clase.inscripciones.filter(
            estado__in=[Inscripcion.Estado.RESERVADA, Inscripcion.Estado.PENDIENTE_PAGO]
        ).select_related("usuario", "periodo").prefetch_related("ocurrencias").order_by("-fecha_inscripcion")
        selected_periodo_id = "all"
    else:
        if periodo_id:
            try:
                selected_periodo = PeriodoCobro.objects.get(pk=int(periodo_id))
            except (ValueError, PeriodoCobro.DoesNotExist):
                selected_periodo = periodo_vigente()
        else:
            selected_periodo = periodo_vigente()
            
        selected_periodo_id = str(selected_periodo.id) if selected_periodo else ""
        
        if selected_periodo:
            inscripciones = clase.inscripciones.filter(
                periodo=selected_periodo,
                estado__in=[Inscripcion.Estado.RESERVADA, Inscripcion.Estado.PENDIENTE_PAGO]
            ).select_related("usuario", "periodo").prefetch_related("ocurrencias").order_by("-fecha_inscripcion")
        else:
            inscripciones = []

    return render(
        request,
        "partials/classes/list/_class_roster_drawer_panel.html",
        {
            "clase": clase,
            "inscripciones": inscripciones,
            "periodos": periodos,
            "selected_periodo_id": selected_periodo_id,
        }
    )


@staff_required
def student_enrollments_drawer(request, user_id):
    from apps.users.models import User
    from apps.payments.models import PeriodoCobro
    from apps.payments.periodos import periodo_vigente
    
    student = get_object_or_404(User, pk=user_id)
    periodos = PeriodoCobro.objects.order_by("-fecha_inicio_periodo")
    periodo_id = request.GET.get("periodo_id")
    
    if periodo_id == "all":
        inscripciones = student.inscripciones.filter(
            estado__in=[Inscripcion.Estado.RESERVADA, Inscripcion.Estado.PENDIENTE_PAGO]
        ).select_related("clase", "clase__disciplina", "clase__sala", "clase__sala__sede", "periodo").order_by("-fecha_inscripcion")
        selected_periodo_id = "all"
    else:
        if periodo_id:
            try:
                selected_periodo = PeriodoCobro.objects.get(pk=int(periodo_id))
            except (ValueError, PeriodoCobro.DoesNotExist):
                selected_periodo = periodo_vigente()
        else:
            selected_periodo = periodo_vigente()
            
        selected_periodo_id = str(selected_periodo.id) if selected_periodo else ""
        
        if selected_periodo:
            inscripciones = student.inscripciones.filter(
                periodo=selected_periodo,
                estado__in=[Inscripcion.Estado.RESERVADA, Inscripcion.Estado.PENDIENTE_PAGO]
            ).select_related("clase", "clase__disciplina", "clase__sala", "clase__sala__sede", "periodo").order_by("-fecha_inscripcion")
        else:
            inscripciones = []

    return render(
        request,
        "partials/classes/list/_student_enrollments_drawer_panel.html",
        {
            "student": student,
            "inscripciones": inscripciones,
            "periodos": periodos,
            "selected_periodo_id": selected_periodo_id,
        }
    )


def _sede_modal_context(form, instance=None):
    editing = instance is not None and instance.pk
    if editing:
        return {
            "form": form,
            "title": "Editar sede",
            "subtitle": "Actualizá el nombre y la dirección.",
            "button_label": "Guardar cambios",
            "action_url": reverse("classes:update_sede", args=[instance.pk]),
        }
    return {
        "form": form,
        "title": "Agregar sede",
        "subtitle": "Ingresá los datos de la nueva sede.",
        "button_label": "Guardar sede",
        "action_url": reverse("classes:create_sede"),
    }


def _render_sede_modal_panel(request, form, instance=None, status=200):
    ctx = _sede_modal_context(form, instance)
    return render(
        request,
        "partials/classes/modals/_sede_modal_panel.html",
        {
            "modal_form": ctx["form"],
            "modal_title": ctx["title"],
            "modal_subtitle": ctx["subtitle"],
            "modal_button_label": ctx["button_label"],
            "action_url": ctx["action_url"],
        },
        status=status,
    )


def _sala_modal_context(form, instance=None):
    editing = instance is not None and instance.pk
    if editing:
        return {
            "form": form,
            "title": "Editar sala",
            "subtitle": "Actualizá nombre, capacidad y sede.",
            "button_label": "Guardar cambios",
            "action_url": reverse("classes:update_sala", args=[instance.pk]),
            "lock_sede": False,
            "selected_sede_id": None,
        }
    return {
        "form": form,
        "title": "Agregar sala",
        "subtitle": "Ingresá los datos de la nueva sala.",
        "button_label": "Guardar sala",
        "action_url": reverse("classes:create_sala"),
        "lock_sede": True,
        "selected_sede_id": None,
    }


def _render_sala_modal_panel(
    request, form, instance=None, *, lock_sede=False, selected_sede_id=None, status=200
):
    ctx = _sala_modal_context(form, instance)
    if instance is None:
        ctx["lock_sede"] = lock_sede
        ctx["selected_sede_id"] = selected_sede_id
    return render(
        request,
        "partials/classes/modals/_sala_modal_panel.html",
        {
            "modal_form": ctx["form"],
            "modal_title": ctx["title"],
            "modal_subtitle": ctx["subtitle"],
            "modal_button_label": ctx["button_label"],
            "action_url": ctx["action_url"],
            "lock_sede": ctx["lock_sede"],
            "selected_sede_id": ctx["selected_sede_id"],
        },
        status=status,
    )


def _disciplina_modal_context(form, instance=None):
    editing = instance is not None and instance.pk
    if editing:
        return {
            "form": form,
            "title": "Editar disciplina",
            "subtitle": "Actualizá el nombre y la descripción.",
            "button_label": "Guardar cambios",
            "action_url": reverse("classes:update_disciplina", args=[instance.pk]),
        }
    return {
        "form": form,
        "title": "Nueva disciplina",
        "subtitle": "Ingresá los datos de la disciplina.",
        "button_label": "Guardar disciplina",
        "action_url": reverse("classes:create_disciplina"),
    }


def _render_disciplina_modal_panel(request, form, instance=None, status=200):
    ctx = _disciplina_modal_context(form, instance)
    return render(
        request,
        "partials/classes/modals/_disciplina_modal_panel.html",
        {
            "modal_form": ctx["form"],
            "modal_title": ctx["title"],
            "modal_subtitle": ctx["subtitle"],
            "modal_button_label": ctx["button_label"],
            "action_url": ctx["action_url"],
        },
        status=status,
    )


def _teacher_modal_context(form, instance=None):
    editing = instance is not None and instance.pk
    if editing:
        return {
            "form": form,
            "title": "Editar profesor",
            "subtitle": "Actualizá nombre y apellido.",
            "button_label": "Guardar cambios",
            "action_url": reverse("classes:update_teacher", args=[instance.pk]),
        }
    return {
        "form": form,
        "title": "Nuevo profesor",
        "subtitle": "Ingresá los datos del profesor.",
        "button_label": "Guardar profesor",
        "action_url": reverse("classes:create_teacher"),
    }


def _render_teacher_modal_panel(request, form, instance=None, status=200):
    ctx = _teacher_modal_context(form, instance)
    return render(
        request,
        "partials/classes/modals/_teacher_modal_panel.html",
        {
            "modal_form": ctx["form"],
            "modal_title": ctx["title"],
            "modal_subtitle": ctx["subtitle"],
            "modal_button_label": ctx["button_label"],
            "action_url": ctx["action_url"],
        },
        status=status,
    )


def _filter_class_queryset(request):
    qs = Class.objects.select_related(
        "disciplina", "sala", "sala__sede", "profesor"
    ).order_by("dia_semana", "hora_inicio")
    qs = apply_text_search(
        qs,
        request.GET.get("q", ""),
        "disciplina__nombre",
        "sala__nombre",
        "sala__sede__nombre",
        "profesor__nombre",
        "profesor__apellido",
    )
    disciplina = request.GET.get("disciplina")
    if disciplina:
        qs = qs.filter(disciplina_id=disciplina)
    sede = request.GET.get("sede")
    if sede:
        qs = qs.filter(sala__sede_id=sede)
    profesor = request.GET.get("profesor")
    if profesor:
        qs = qs.filter(profesor_id=profesor)
    dia = request.GET.get("dia_semana")
    if dia not in (None, ""):
        qs = qs.filter(dia_semana=dia)
    estado = request.GET.get("estado")
    if estado:
        qs = qs.filter(estado=estado)
    return qs


def _class_rows_context(request):
    if request.GET.get("cleared"):
        return {
            "classes": [],
            "searched": False,
            "q": "",
            "page_obj": None,
        }
    qs = _filter_class_queryset(request)
    
    page_number = request.GET.get("page") or 1
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(page_number)
    
    from apps.payments.models import PeriodoCobro, PrecioClase
    from django.utils import timezone
    hoy = timezone.localdate()
    periodo = PeriodoCobro.objects.filter(fecha_fin_periodo__gte=hoy).order_by('fecha_inicio_periodo').first()
    precios = {p.clase_id: p.monto for p in PrecioClase.objects.filter(periodo=periodo)} if periodo else {}
    
    for c in page_obj:
        c.precio_actual = precios.get(c.id)
        
    return {
        "classes": page_obj,
        "searched": True,
        "q": request.GET.get("q", ""),
        "page_obj": page_obj,
    }


def _all_class_rows_context():
    qs = Class.objects.select_related(
        "disciplina", "sala", "sala__sede", "profesor"
    ).order_by("dia_semana", "hora_inicio")
    
    from apps.payments.models import PeriodoCobro, PrecioClase
    from django.utils import timezone
    hoy = timezone.localdate()
    periodo = PeriodoCobro.objects.filter(fecha_fin_periodo__gte=hoy).order_by('fecha_inicio_periodo').first()
    precios = {p.clase_id: p.monto for p in PrecioClase.objects.filter(periodo=periodo)} if periodo else {}
    
    clases = list(qs)
    for c in clases:
        c.precio_actual = precios.get(c.id)
        
    return {
        "classes": clases,
        "searched": True,
        "q": "",
    }


CLASS_LIST_VIEW_TABS = [
    {"id": "lista", "label": "Listado"},
    {"id": "precios", "label": "Precios"},
]

CATALOG_VIEW_TABS = [
    {"id": "disciplinas", "label": "Disciplinas"},
    {"id": "profesores", "label": "Profesores"},
    {"id": "sedes_salas", "label": "Sedes y salas"},
]


@staff_required
def class_list(request):
    is_admin = request.user.rol == "ADMIN"
    tabs = CLASS_LIST_VIEW_TABS if is_admin else [t for t in CLASS_LIST_VIEW_TABS if t["id"] != "precios"]

    tab = request.GET.get("tab", "lista")
    if tab not in {t["id"] for t in tabs}:
        tab = "lista"
    return render(
        request,
        "classes/class_list.html",
        {
            "filter_url": reverse("classes:class_rows"),
            "disciplinas": Disciplina.objects.order_by("nombre"),
            "sedes": Sede.objects.order_by("nombre"),
            "profesores": Teacher.objects.order_by("nombre", "apellido"),
            "weekday_choices": Class.WEEKDAY_CHOICES,
            "estado_choices": Class.ESTADO_CHOICES,
            "view_tabs": tabs,
            "initial_tab": tab,
            "class_rows_searched": False,
            "is_admin": is_admin,
        },
    )

@admin_required
def precios_rows(request):
    from apps.payments.models import PeriodoCobro, PrecioClase
    from django.utils import timezone
    hoy = timezone.localdate()
    
    periodos_futuros = PeriodoCobro.objects.filter(fecha_fin_periodo__gte=hoy).order_by('fecha_inicio_periodo')
    periodo_id = request.GET.get('periodo_id')
    
    clases_con_precio = []
    periodo = None
    
    if periodo_id:
        periodo = PeriodoCobro.objects.filter(pk=periodo_id).first()
        
    # Check if this is a filter submission or active search
    is_search = request.headers.get("HX-Trigger") == "precios-filters-form" or any(request.GET.get(k) for k in ['q', 'disciplina', 'sede', 'profesor', 'dia_semana', 'estado'])
    
    if periodo or is_search:
        clases = _filter_class_queryset(request)
        precios = {p.clase_id: p.monto for p in PrecioClase.objects.filter(periodo=periodo)} if periodo else {}
        for c in clases:
            clases_con_precio.append({
                'clase': c,
                'precio': precios.get(c.id, '')
            })
            
    return render(
        request,
        "partials/classes/rows/_precios_rows.html",
        {
            "clases_con_precio": clases_con_precio,
            "periodo": periodo,
            "periodos_futuros": periodos_futuros,
            "periodo_id": periodo_id,
            "searched": bool(periodo) or is_search,
        }
    )

@admin_required
def apply_mass_price_increase(request):
    if request.method != "POST":
        return redirect("classes:class_list")
        
    from apps.payments.models import PeriodoCobro, PrecioClase
    from decimal import Decimal
    
    periodo_id = request.POST.get('periodo_id')
    tipo_aumento = request.POST.get('tipo_aumento', 'porcentaje')
    porcentaje = request.POST.get('porcentaje')
    monto_fijo = request.POST.get('monto_fijo')
    
    if tipo_aumento == 'porcentaje':
        monto_fijo = None
    else:
        porcentaje = None
    
    if not periodo_id or (not porcentaje and not monto_fijo):
        return _hx_ok_or_redirect(request, message="Faltan parámetros", level="error", redirect_to="classes:class_list")
        
    try:
        porcentaje_val = Decimal(porcentaje) if porcentaje else None
        monto_fijo_val = Decimal(monto_fijo) if monto_fijo else None
    except Exception:
        return _hx_ok_or_redirect(request, message="Valor numérico inválido", level="error", redirect_to="classes:class_list")
        
    periodo = PeriodoCobro.objects.filter(pk=periodo_id).first()
    if not periodo:
        return _hx_ok_or_redirect(request, message="Período no encontrado", level="error", redirect_to="classes:class_list")
        
    # Get affected classes from filters using POST directly since HTMX sends them there
    clases = _filter_class_queryset(request)
    clases_ids = list(clases.values_list('id', flat=True))
    
    if not clases_ids:
        return _hx_ok_or_redirect(request, message="No hay clases afectadas por los filtros.", level="info", redirect_to="classes:class_list")
        
    actualizados = 0
    creados = 0
    precios_existentes = {p.clase_id: p for p in PrecioClase.objects.filter(periodo=periodo, clase_id__in=clases_ids)}
    
    for clase_id in clases_ids:
        p = precios_existentes.get(clase_id)
        if p:
            if porcentaje_val:
                nuevo_monto = p.monto * (Decimal('1') + (porcentaje_val / Decimal('100')))
                p.monto = round(nuevo_monto)
                p.save()
                actualizados += 1
            elif monto_fijo_val:
                p.monto = p.monto + monto_fijo_val
                p.save()
                actualizados += 1
        else:
            # We must create it
            if monto_fijo_val:
                # Si es un monto fijo y no tenia precio, simplemente lo creamos si era positivo
                # O si quieren crear un precio con monto fijo puro.
                PrecioClase.objects.create(clase_id=clase_id, periodo=periodo, monto=max(Decimal('0'), monto_fijo_val))
                creados += 1
            elif porcentaje_val:
                # Buscamos el precio mas reciente
                ultimo_precio = PrecioClase.objects.filter(clase_id=clase_id, periodo__fecha_inicio_periodo__lt=periodo.fecha_inicio_periodo).order_by('-periodo__fecha_inicio_periodo').first()
                base = ultimo_precio.monto if ultimo_precio else Decimal('0')
                if base > 0:
                    nuevo_monto = base * (Decimal('1') + (porcentaje_val / Decimal('100')))
                    PrecioClase.objects.create(clase_id=clase_id, periodo=periodo, monto=max(Decimal('0'), round(nuevo_monto)))
                    creados += 1
        
    if creados > 0:
        msg = f"Precios actualizados: {actualizados} modificados y {creados} creados para el período {periodo.nombre}."
    else:
        msg = f"Precios actualizados: {actualizados} modificados para el período {periodo.nombre}."

    return _hx_ok_or_redirect(
        request,
        message=msg,
        trigger="reloadPrecios",
        redirect_to="classes:class_list"
    )

@admin_required
def save_class_price(request, class_id):
    from apps.payments.models import PeriodoCobro, PrecioClase
    
    periodo_id = request.POST.get('periodo_id')
    monto = request.POST.get('monto')
    
    if not periodo_id or not monto:
        return HttpResponseBadRequest("Faltan parámetros")
        
    periodo = PeriodoCobro.objects.filter(pk=periodo_id).first()
    clase = Class.objects.filter(pk=class_id).first()
    
    if not periodo or not clase:
        return HttpResponseBadRequest("Clase o período inválido")
        
    PrecioClase.objects.update_or_create(
        clase=clase,
        periodo=periodo,
        defaults={'monto': monto}
    )
    
    return HttpResponse(monto) # Return the updated amount to be swapped by HTMX


@admin_required
def class_price_for_period(request, class_id):
    from apps.payments.models import PeriodoCobro, PrecioClase
    from .forms import ClassForm
    from django.http import HttpResponse
    
    periodo_id = request.GET.get('mes_a_aplicar')
    if not periodo_id:
        return HttpResponse("")
        
    periodo = PeriodoCobro.objects.filter(pk=periodo_id).first()
    clase = Class.objects.filter(pk=class_id).first()
    
    precio = None
    if periodo and clase:
        precio_obj = PrecioClase.objects.filter(clase=clase, periodo=periodo).first()
        if precio_obj:
            precio = precio_obj.monto
            
    form = ClassForm(instance=clase, initial={'precio': precio})
    return HttpResponse(str(form['precio']))


@staff_required
def class_rows(request):
    ctx = _class_rows_context(request)
    ctx["is_admin"] = request.user.rol == "ADMIN"
    return render(
        request,
        "partials/classes/_class_table_panel.html",
        ctx,
    )


@admin_required
def locations_list(request):
    sede_id = request.GET.get("sede_id")
    suffix = f"&sede_id={sede_id}" if sede_id else ""
    return redirect(reverse("classes:catalog") + "?tab=sedes_salas" + suffix)


@admin_required
def sala_rows(request):
    sede_id = request.GET.get("sede_id")
    if not sede_id:
        return render(
            request,
            "partials/classes/rows/_sala_rows.html",
            {
                "salas": Sala.objects.none(),
                "sede": None,
            },
        )
    sede = get_object_or_404(Sede, pk=sede_id)
    salas = Sala.objects.filter(sede=sede).order_by("nombre")
    return render(
        request,
        "partials/classes/rows/_sala_rows.html",
        {
            "salas": salas,
            "sede": sede,
        },
    )


@admin_required
def catalog(request):
    tab = request.GET.get("tab", "disciplinas")
    valid_tabs = [t["id"] for t in CATALOG_VIEW_TABS]
    if tab not in valid_tabs:
        tab = "disciplinas"

    sedes = Sede.objects.all().order_by("nombre")
    selected_sede_id = request.GET.get("sede_id")
    if selected_sede_id:
        try:
            selected_sede_id = int(selected_sede_id)
        except (ValueError, TypeError):
            selected_sede_id = sedes[0].id if sedes.exists() else None
    elif sedes.exists():
        selected_sede_id = sedes[0].id
    else:
        selected_sede_id = None

    return render(
        request,
        "classes/catalog.html",
        {
            "disciplina_form": DisciplinaForm(),
            "teacher_form": TeacherForm(),
            "create_disciplina_url": reverse("classes:create_disciplina"),
            "create_teacher_url": reverse("classes:create_teacher"),
            "view_tabs": CATALOG_VIEW_TABS,
            "initial_tab": tab,
            "sedes": sedes,
            "selected_sede_id": selected_sede_id,
        },
    )


@admin_required
def disciplina_rows(request):
    q = request.GET.get("q", "")
    disciplinas = apply_text_search(
        Disciplina.objects.all().order_by("nombre"), q, "nombre", "descripcion"
    )
    return render(
        request,
        "partials/classes/rows/_disciplina_rows.html",
        {
            "disciplinas": disciplinas,
            "searched": True,
            "q": request.GET.get("q", ""),
        },
    )


@admin_required
def teacher_rows(request):
    q = request.GET.get("q", "")
    teachers = apply_text_search(
        Teacher.objects.all().order_by("nombre", "apellido"), q, "nombre", "apellido"
    )
    return render(
        request,
        "partials/classes/rows/_teacher_rows.html",
        {
            "teachers": teachers,
            "searched": True,
            "q": request.GET.get("q", ""),
        },
    )


@admin_required
def class_modal(request, class_id=None):
    if class_id is not None:
        instance = get_object_or_404(
            Class.objects.select_related("sala__sede"),
            pk=class_id,
        )
        form = ClassForm(instance=instance, initial=_edit_initial_for_class(instance))
    else:
        instance = None
        form = ClassForm()
    return _render_class_drawer(request, form, instance)


@admin_required
def salas_por_sede(request):
    sede_id = request.GET.get("sede")
    sala_id = request.GET.get("sala")
    form = ClassForm()
    if sede_id:
        try:
            form.fields["sala"].queryset = Sala.objects.filter(
                sede_id=int(sede_id)
            ).order_by("nombre")
            if sala_id:
                try:
                    sala_pk = int(sala_id)
                    if form.fields["sala"].queryset.filter(pk=sala_pk).exists():
                        form.fields["sala"].initial = sala_pk
                except ValueError, TypeError:
                    pass
        except ValueError, TypeError:
            form.fields["sala"].queryset = Sala.objects.none()
    else:
        form.fields["sala"].queryset = Sala.objects.none()
    return render(request, "partials/classes/shared/_sala_field.html", {"form": form})


@admin_required
def create_class(request):
    if request.method != "POST":
        return redirect("classes:class_list")
    form = ClassForm(request.POST)
    if form.is_valid():
        form.save()
        return _hx_ok_or_redirect(
            request,
            message="La clase fue publicada correctamente.",
            redirect_to="classes:class_list",
            close_modal="classDrawerOpen",
            refresh=_class_rows_refresh(),
        )
    if request.headers.get("HX-Request"):
        return _render_class_drawer(request, form)
    return redirect("classes:class_list")


@admin_required
def delete_class(request, class_id):
    if request.method != "POST":
        return redirect("classes:class_list")
    clase = get_object_or_404(Class, pk=class_id)
    try:
        nombre = str(clase)
        clase.delete()
        return _hx_ok_or_redirect(
            request,
            message=f"La clase «{nombre}» fue eliminada.",
            redirect_to="classes:class_list",
            refresh=_class_rows_refresh(),
        )
    except ProtectedError:
        return _hx_ok_or_redirect(
            request,
            message="No se puede eliminar esta clase porque tiene datos asociados.",
            redirect_to="classes:class_list",
            level="error",
        )


@admin_required
def toggle_class_pause(request, class_id):
    if request.method != "POST":
        return redirect("classes:class_list")
    clase = get_object_or_404(Class, pk=class_id)
    if clase.estado == "disponible":
        clase.estado = "pausada"
        msg = f"La clase «{clase}» fue pausada."
    else:
        clase.estado = "disponible"
        msg = f"La clase «{clase}» está disponible nuevamente."
    clase.save()
    return _hx_ok_or_redirect(
        request,
        message=msg,
        redirect_to="classes:class_list",
        refresh=_class_rows_refresh(),
    )


@admin_required
def update_class(request, class_id):
    if request.method != "POST":
        return redirect("classes:class_list")
    instance = get_object_or_404(Class, pk=class_id)
    form = ClassForm(request.POST, instance=instance)
    if form.is_valid():
        form.save()
        return _hx_ok_or_redirect(
            request,
            message=f"La clase «{instance}» fue actualizada correctamente.",
            redirect_to="classes:class_list",
            close_modal="classDrawerOpen",
            refresh=_class_rows_refresh(),
        )
    if request.headers.get("HX-Request"):
        return _render_class_drawer(request, form, instance)
    return redirect("classes:class_list")


@admin_required
def sede_modal(request, sede_id=None):
    if sede_id is not None:
        instance = get_object_or_404(Sede, pk=sede_id)
        form = SedeForm(instance=instance)
    else:
        instance = None
        form = SedeForm()
    return _render_sede_modal_panel(request, form, instance)


@admin_required
def sala_modal(request, sala_id=None):
    if sala_id is not None:
        instance = get_object_or_404(Sala, pk=sala_id)
        form = SalaForm(instance=instance)
        return _render_sala_modal_panel(request, form, instance)
    sede_id = request.GET.get("sede_id")
    initial = {}
    lock_sede = False
    if sede_id:
        try:
            initial["sede"] = int(sede_id)
            lock_sede = True
        except (ValueError, TypeError):
            pass
    form = SalaForm(initial=initial)
    return _render_sala_modal_panel(
        request,
        form,
        lock_sede=lock_sede,
        selected_sede_id=initial.get("sede"),
    )


@admin_required
def create_sede(request):
    if request.method != "POST":
        return redirect(reverse("classes:catalog") + "?tab=sedes_salas")
    form = SedeForm(request.POST)
    if form.is_valid():
        sede = form.save()
        return _hx_ok_or_redirect(
            request,
            message=f"La sede «{sede.nombre}» fue creada.",
            redirect_to=reverse("classes:catalog") + "?tab=sedes_salas",
            close_modal="sedeModalOpen",
            locations_reload=(
                reverse("classes:catalog") + f"?tab=sedes_salas&sede_id={sede.pk}"
            ),
        )
    if request.headers.get("HX-Request"):
        return _render_sede_modal_panel(request, form)
    return redirect(reverse("classes:catalog") + "?tab=sedes_salas")


@admin_required
def update_sede(request, sede_id):
    if request.method != "POST":
        return redirect(reverse("classes:catalog") + "?tab=sedes_salas")
    instance = get_object_or_404(Sede, pk=sede_id)
    form = SedeForm(request.POST, instance=instance)
    if form.is_valid():
        sede = form.save()
        return _hx_ok_or_redirect(
            request,
            message=f"La sede «{sede.nombre}» fue actualizada.",
            redirect_to=reverse("classes:catalog") + "?tab=sedes_salas",
            close_modal="sedeModalOpen",
            locations_reload=(
                reverse("classes:catalog") + f"?tab=sedes_salas&sede_id={sede.pk}"
            ),
        )
    if request.headers.get("HX-Request"):
        return _render_sede_modal_panel(request, form, instance)
    return redirect(reverse("classes:catalog") + "?tab=sedes_salas")


@admin_required
def create_sala(request):
    if request.method != "POST":
        return redirect(reverse("classes:catalog") + "?tab=sedes_salas")
    form = SalaForm(request.POST)
    if form.is_valid():
        sala = form.save()
        sede = sala.sede
        return _hx_ok_or_redirect(
            request,
            message=f"La sala «{sala.nombre}» fue creada.",
            redirect_to=reverse("classes:catalog") + "?tab=sedes_salas",
            close_modal="salaModalOpen",
            refresh=_sala_rows_refresh(sede.pk),
        )
    sede_id = request.POST.get("sede")
    if request.headers.get("HX-Request"):
        return _render_sala_modal_panel(
            request,
            form,
            lock_sede=bool(sede_id),
            selected_sede_id=int(sede_id) if sede_id and str(sede_id).isdigit() else None,
        )
    return redirect(reverse("classes:catalog") + "?tab=sedes_salas")


@admin_required
def update_sala(request, sala_id):
    if request.method != "POST":
        return redirect(reverse("classes:catalog") + "?tab=sedes_salas")
    instance = get_object_or_404(Sala, pk=sala_id)
    form = SalaForm(request.POST, instance=instance)
    if form.is_valid():
        sala = form.save()
        return _hx_ok_or_redirect(
            request,
            message=f"La sala «{sala.nombre}» fue actualizada.",
            redirect_to=reverse("classes:catalog") + "?tab=sedes_salas",
            close_modal="salaModalOpen",
            refresh=_sala_rows_refresh(sala.sede_id),
        )
    if request.headers.get("HX-Request"):
        return _render_sala_modal_panel(request, form, instance)
    return redirect(reverse("classes:catalog") + "?tab=sedes_salas")


@admin_required
def disciplina_modal(request, disciplina_id=None):
    if disciplina_id is not None:
        instance = get_object_or_404(Disciplina, pk=disciplina_id)
        form = DisciplinaForm(instance=instance)
    else:
        instance = None
        form = DisciplinaForm()
    return _render_disciplina_modal_panel(request, form, instance)


@admin_required
def create_disciplina(request):
    if request.method != "POST":
        return redirect(reverse("classes:catalog") + "?tab=disciplinas")
    form = DisciplinaForm(request.POST)
    if form.is_valid():
        disciplina = form.save()
        return _hx_ok_or_redirect(
            request,
            message=f"La disciplina «{disciplina.nombre}» fue creada.",
            redirect_to=reverse("classes:catalog") + "?tab=disciplinas",
            close_modal="disciplinaModalOpen",
            refresh=_disciplina_rows_refresh(),
        )
    if request.headers.get("HX-Request"):
        return _render_disciplina_modal_panel(request, form)
    return redirect(reverse("classes:catalog") + "?tab=disciplinas")


@admin_required
def update_disciplina(request, disciplina_id):
    if request.method != "POST":
        return redirect(reverse("classes:catalog") + "?tab=disciplinas")
    instance = get_object_or_404(Disciplina, pk=disciplina_id)
    form = DisciplinaForm(request.POST, instance=instance)
    if form.is_valid():
        disciplina = form.save()
        return _hx_ok_or_redirect(
            request,
            message=f"La disciplina «{disciplina.nombre}» fue actualizada.",
            redirect_to=reverse("classes:catalog") + "?tab=disciplinas",
            close_modal="disciplinaModalOpen",
            refresh=_disciplina_rows_refresh(),
        )
    if request.headers.get("HX-Request"):
        return _render_disciplina_modal_panel(request, form, instance)
    return redirect(reverse("classes:catalog") + "?tab=disciplinas")


@admin_required
def teacher_modal(request, teacher_id=None):
    if teacher_id is not None:
        instance = get_object_or_404(Teacher, pk=teacher_id)
        form = TeacherForm(instance=instance)
    else:
        instance = None
        form = TeacherForm()
    return _render_teacher_modal_panel(request, form, instance)


@admin_required
def create_teacher(request):
    if request.method != "POST":
        return redirect(reverse("classes:catalog") + "?tab=profesores")
    form = TeacherForm(request.POST)
    if form.is_valid():
        teacher = form.save()
        return _hx_ok_or_redirect(
            request,
            message=f"El profesor «{teacher.nombre} {teacher.apellido}» fue creado.",
            redirect_to=reverse("classes:catalog") + "?tab=profesores",
            close_modal="teacherModalOpen",
            refresh=_teacher_rows_refresh(),
        )
    if request.headers.get("HX-Request"):
        return _render_teacher_modal_panel(request, form)
    return redirect(reverse("classes:catalog") + "?tab=profesores")


@admin_required
def update_teacher(request, teacher_id):
    if request.method != "POST":
        return redirect(reverse("classes:catalog") + "?tab=profesores")
    instance = get_object_or_404(Teacher, pk=teacher_id)
    form = TeacherForm(request.POST, instance=instance)
    if form.is_valid():
        teacher = form.save()
        return _hx_ok_or_redirect(
            request,
            message=f"El profesor «{teacher.nombre} {teacher.apellido}» fue actualizado.",
            redirect_to=reverse("classes:catalog") + "?tab=profesores",
            close_modal="teacherModalOpen",
            refresh=_teacher_rows_refresh(),
        )
    if request.headers.get("HX-Request"):
        return _render_teacher_modal_panel(request, form, instance)
    return redirect(reverse("classes:catalog") + "?tab=profesores")


@admin_required
def delete_sede(request, sede_id):
    if request.method != "POST":
        return redirect(reverse("classes:catalog") + "?tab=sedes_salas")
    sede = get_object_or_404(Sede, pk=sede_id)
    try:
        nombre = sede.nombre
        sede.delete()
        return _hx_ok_or_redirect(
            request,
            message=f"La sede «{nombre}» fue eliminada.",
            redirect_to=reverse("classes:catalog") + "?tab=sedes_salas",
            locations_reload=reverse("classes:catalog") + "?tab=sedes_salas",
        )
    except ProtectedError:
        return _hx_ok_or_redirect(
            request,
            message=f"No se puede eliminar la sede «{sede.nombre}» porque tiene salas con clases asignadas.",
            redirect_to=reverse("classes:catalog") + "?tab=sedes_salas",
            level="error",
        )


@admin_required
def delete_sala(request, sala_id):
    if request.method != "POST":
        return redirect(reverse("classes:catalog") + "?tab=sedes_salas")
    sala = get_object_or_404(Sala, pk=sala_id)
    sede_id = sala.sede_id
    try:
        nombre = sala.nombre
        sala.delete()
        return _hx_ok_or_redirect(
            request,
            message=f"La sala «{nombre}» fue eliminada.",
            redirect_to=reverse("classes:catalog") + "?tab=sedes_salas",
            refresh=_sala_rows_refresh(sede_id),
        )
    except ProtectedError:
        return _hx_ok_or_redirect(
            request,
            message=f"No se puede eliminar la sala «{sala.nombre}» porque tiene clases asignadas.",
            redirect_to=reverse("classes:catalog") + "?tab=sedes_salas",
            level="error",
        )


@admin_required
def delete_disciplina(request, disciplina_id):
    if request.method != "POST":
        return redirect(reverse("classes:catalog") + "?tab=disciplinas")
    disciplina = get_object_or_404(Disciplina, pk=disciplina_id)
    try:
        nombre = disciplina.nombre
        disciplina.delete()
        return _hx_ok_or_redirect(
            request,
            message=f"La disciplina «{nombre}» fue eliminada.",
            redirect_to=reverse("classes:catalog") + "?tab=disciplinas",
            refresh=_disciplina_rows_refresh(),
        )
    except ProtectedError:
        return _hx_ok_or_redirect(
            request,
            message=f"No se puede eliminar «{disciplina.nombre}» porque tiene clases asignadas.",
            redirect_to=reverse("classes:catalog") + "?tab=disciplinas",
            level="error",
        )


@admin_required
def delete_teacher(request, teacher_id):
    if request.method != "POST":
        return redirect(reverse("classes:catalog") + "?tab=profesores")
    teacher = get_object_or_404(Teacher, pk=teacher_id)
    try:
        nombre = str(teacher)
        teacher.delete()
        return _hx_ok_or_redirect(
            request,
            message=f"El profesor «{nombre}» fue eliminado.",
            redirect_to=reverse("classes:catalog") + "?tab=profesores",
            refresh=_teacher_rows_refresh(),
        )
    except ProtectedError:
        return _hx_ok_or_redirect(
            request,
            message=f"No se puede eliminar «{teacher}» porque tiene clases asignadas.",
            redirect_to=reverse("classes:catalog") + "?tab=profesores",
            level="error",
        )


# ── Cliente: actividades → clase → pago ──────────────────────────────────────

@login_required
def browse_clases(request):
    return redirect("classes:actividades")


@login_required
def actividades(request):
    actividades_url = reverse("classes:actividades")
    session_urls = _flow_session_urls(request)

    constancia_mensajes = {
        "RECHAZADA": (
            "Tu perfil no tiene una constancia aprobada, y no podes hacer "
            "una reserva hasta tener una. Para tener una constancia "
            "aprobada, acercate a un local para presentarla."
        ),
        "PENDIENTE": (
            "Tu perfil tiene una constancia pendiente. Espera a que un "
            "administrador apruebe tu constancia para hacer una reserva."
        ),
    }
    constancia_bloqueo = constancia_mensajes.get(request.user.estado_constancia)
    if constancia_bloqueo:
        return render(
            request,
            "classes/actividades.html",
            {
                "constancia_bloqueo": constancia_bloqueo,
                "flow_step": "actividades",
                "flow_title": "Actividades",
                **build_flow_stepper_context("actividades", actividades_url=actividades_url),
            },
        )

    disciplinas = list(cliente.disciplinas_con_clases())
    for disciplina in disciplinas:
        disciplina.cronograma_url = reverse(
            "classes:cronograma", args=[disciplina.pk]
        )
        n = cliente.clases_disponibles_qs().filter(disciplina=disciplina).count()
        disciplina.num_clases = n
        disciplina.lineas = [disciplina.descripcion] if disciplina.descripcion else []
        disciplina.badge_horarios = f"{n} horario{'s' if n != 1 else ''}" if n else ""
    return render(
        request,
        "classes/actividades.html",
        {
            "disciplinas": disciplinas,
            "flow_step": "actividades",
            "flow_title": "Actividades",
            "flow_subtitle": "Disciplina, horario, fecha y pago: cuatro pasos para reservar tu lugar.",
            **build_flow_stepper_context(
                "actividades",
                actividades_url=actividades_url,
                horarios_url=session_urls.get("horarios_url"),
                clase_url=session_urls.get("clase_url"),
                pago_url=session_urls.get("pago_url"),
            ),
        },
    )


@login_required
def cronograma_disciplina(request, disciplina_id):
    disciplina = get_object_or_404(Disciplina, pk=disciplina_id)
    clases = cliente.clases_disponibles_qs().filter(disciplina=disciplina)
    actividades_url = reverse("classes:actividades")
    horarios_url = reverse("classes:cronograma", args=[disciplina.pk])
    request.session["flow_disciplina_id"] = disciplina.pk
    session_urls = _flow_session_urls(request, disciplina_id=disciplina.pk)

    if clases.count() == 1:
        return redirect("classes:detalle", clase_id=clases.first().pk)

    clases_info = []
    for c in clases.order_by("dia_semana", "hora_inicio"):
        inicio = proxima_ocurrencia(c)
        cupo_resumen = cliente.resumen_cupo_inscripcion(c, usuario=request.user)
        hay_lugar = cupo_resumen["puede_agregar_reserva"]
        puede_espera = cupo_resumen.get("puede_anotarse_espera", False)

        if hay_lugar:
            badge = "Hay lugar"
            badge_tone = "ok"
        elif puede_espera:
            badge = "Lista de espera"
            badge_tone = "wait"
        else:
            badge = "Agotada"
            badge_tone = "danger"

        clases_info.append(
            {
                "detalle_url": reverse("classes:detalle", args=[c.pk]),
                "titulo": c.get_dia_semana_display(),
                "proximo_inicio": inicio,
                "duracion_minutos": c.duracion_minutos,
                "lineas": [f"{c.sala.nombre} · {c.sala.sede.nombre}"],
                "hay_lugar": hay_lugar,
                "badge": badge,
                "badge_tone": badge_tone,
            }
        )

    return render(
        request,
        "classes/cronograma.html",
        {
            "disciplina": disciplina,
            "clases_info": clases_info,
            "flow_step": "horarios",
            "flow_back_url": actividades_url,
            "flow_back_label": "Actividades",
            "flow_title": disciplina.nombre,
            "flow_subtitle": "Cada tarjeta es un día y horario fijo. Elegí el que mejor te quede.",
            "actividades_back_url": actividades_url,
            **build_flow_stepper_context(
                "horarios",
                actividades_url=actividades_url,
                horarios_url=horarios_url,
                clase_url=session_urls.get("clase_url"),
                pago_url=session_urls.get("pago_url"),
            ),
        },
    )


@login_required
def detalle_clase(request, clase_id):
    clase = get_object_or_404(
        cliente.clases_disponibles_qs(),
        pk=clase_id,
    )
    from django.template.loader import render_to_string

    info = cliente.info_clase_para_usuario(clase, request.user, request)
    actividades_url = reverse("classes:actividades")
    horarios_url = reverse("classes:cronograma", args=[clase.disciplina_id])
    clase_url = reverse("classes:detalle", args=[clase.id])
    request.session["flow_disciplina_id"] = clase.disciplina_id
    request.session["flow_clase_disciplina_id"] = clase.disciplina_id
    request.session["flow_clase_id"] = clase.id
    session_urls = _flow_session_urls(request, disciplina_id=clase.disciplina_id)

    # Para el stepper global tomamos la primer inscripción "pagable" del usuario:
    # primero la que esté con pago iniciado (`en_pago`), si no la primera
    # `pendiente_pago`. Si no hay ninguna, cae al `pago_url` de sesión.
    pago_url = None
    pagable = next(
        (
            it
            for it in info["inscripciones_activas"]
            if it["estado_ui"] == "en_pago"
        ),
        None,
    ) or next(
        (
            it
            for it in info["inscripciones_activas"]
            if it["estado_ui"] == "pendiente_pago"
        ),
        None,
    )
    if pagable:
        pago_url = reverse(
            "payments:seleccion_pago",
            args=[pagable["inscripcion"].id],
        )
    else:
        pago_url = session_urls.get("pago_url")

    if pago_url:
        request.session["flow_pago_url"] = pago_url

    if info["tiene_proximo_inicio"]:
        flow_subtitle = render_to_string(
            "partials/cliente/flow/_fecha_hora.html",
            {"dt": info["proximo_inicio"], "con_ano": False},
        ).strip()
    else:
        flow_subtitle = info["subtitulo"]

    return render(
        request,
        "classes/detalle_clase.html",
        {
            "info": info,
            "periodos_inscripcion_data": info["periodos_inscripcion"],
            "flow_step": "clase",
            "flow_back_url": horarios_url,
            "flow_back_label": clase.disciplina.nombre,
            "flow_title": clase.disciplina.nombre,
            "flow_subtitle": flow_subtitle or "Revisá los datos y elegí cómo inscribirte.",
            **build_flow_stepper_context(
                "clase",
                actividades_url=actividades_url,
                horarios_url=horarios_url,
                clase_url=clase_url,
                pago_url=pago_url,
            ),
        },
    )


def _tipo_inscripcion_desde_post(request):
    tipo = request.POST.get("tipo", Inscripcion.Tipo.CLASE_SUELTA)
    if tipo not in Inscripcion.Tipo.values:
        return Inscripcion.Tipo.CLASE_SUELTA
    return tipo


def _manejar_inscripcion_duplicada(request, exc: InscripcionDuplicada, clase_id):
    from apps.payments.inscripcion_pago import inscripcion_tiene_intento_pago

    if exc.pendiente_pago:
        if inscripcion_tiene_intento_pago(exc.inscripcion):
            messages.info(request, "Ya tenés el pago de esta clase pendiente.")
            return redirect(
                "payments:seleccion_pago", inscripcion_id=exc.inscripcion.id
            )
        try:
            services.cancelar_reserva(exc.inscripcion.id, request.user)
        except services.ReservaError:
            pass
        return None
    if exc.reservada:
        messages.info(request, "Ya tenés esta clase reservada.")
        return redirect("classes:detalle", clase_id=clase_id)
    if exc.en_lista_espera:
        messages.warning(request, "Ya estás en la lista de espera de esta clase.")
    else:
        messages.warning(request, str(exc))
    return redirect("classes:detalle", clase_id=clase_id)


def _periodo_desde_post(request, tipo):
    from apps.payments.periodos import periodos_elegibles_para

    periodo_id = request.POST.get("periodo_id")
    elegibles = {str(p.id): p for p in periodos_elegibles_para(tipo)}
    if periodo_id and periodo_id in elegibles:
        return elegibles[periodo_id]
    if len(elegibles) == 1:
        return next(iter(elegibles.values()))
    raise services.ReservaError("Elegí el período de cobro para continuar.")


def _fecha_clase_desde_post(request, clase_id):
    from django.utils.dateparse import parse_datetime

    from apps.classes.models import Class
    from apps.classes.services import fecha_clase_elegible, ocurrencias_clase_en_ventana
    from apps.payments.periodos import periodo_conteniendo_fecha

    raw = request.POST.get("fecha_clase")
    if not raw:
        ocurrencias = ocurrencias_clase_en_ventana(
            get_object_or_404(Class, pk=clase_id, estado="disponible")
        )
        if len(ocurrencias) == 1:
            return ocurrencias[0][0]
        raise services.ReservaError("Elegí la fecha de la clase para continuar.")

    dt = parse_datetime(raw)
    if dt is None:
        raise services.ReservaError("La fecha de la clase no es válida.")
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    dt = timezone.localtime(dt).replace(microsecond=0)

    clase = get_object_or_404(Class, pk=clase_id, estado="disponible")
    if not fecha_clase_elegible(clase, dt):
        raise services.ReservaError("La fecha elegida no está disponible.")

    periodo = periodo_conteniendo_fecha(timezone.localdate(dt))
    if not periodo:
        raise services.ReservaError("No hay período de cobro para esa fecha.")
    return dt, periodo


def _ir_a_pantalla_pago(request, clase_id):
    """Guarda modalidad y período en sesión; la inscripción se crea al intentar pagar."""
    from apps.payments.inscripcion_pago import guardar_intencion_pago

    fecha_clase = None
    try:
        tipo = _tipo_inscripcion_desde_post(request)
        if tipo == Inscripcion.Tipo.CLASE_SUELTA:
            fecha_clase, periodo = _fecha_clase_desde_post(request, clase_id)
        else:
            periodo = _periodo_desde_post(request, tipo)
        services.validar_intencion_inscripcion(
            request.user, clase_id, periodo, tipo, fecha_clase=fecha_clase
        )
    except InscripcionDuplicada as exc:
        redirect_resp = _manejar_inscripcion_duplicada(request, exc, clase_id)
        if redirect_resp is not None:
            return redirect_resp
        tipo = _tipo_inscripcion_desde_post(request)
        if tipo == Inscripcion.Tipo.CLASE_SUELTA:
            fecha_clase, periodo = _fecha_clase_desde_post(request, clase_id)
        else:
            fecha_clase = None
            periodo = _periodo_desde_post(request, tipo)
    except services.ReservaError as exc:
        messages.error(request, str(exc))
        return redirect("classes:detalle", clase_id=clase_id)

    guardar_intencion_pago(
        request,
        clase_id=clase_id,
        periodo_id=periodo.id,
        tipo=tipo,
        fecha_clase=fecha_clase,
    )
    return redirect("payments:seleccion_pago_clase", clase_id=clase_id)


def _reservar_desde_detalle(request, clase_id):
    from apps.payments.periodos import requiere_precola_suelta

    clase = get_object_or_404(Class, pk=clase_id, estado="disponible")
    tipo = _tipo_inscripcion_desde_post(request)
    fecha_clase = None
    try:
        if tipo == Inscripcion.Tipo.CLASE_SUELTA:
            fecha_clase, periodo = _fecha_clase_desde_post(request, clase_id)
        else:
            periodo = _periodo_desde_post(request, tipo)
    except services.ReservaError as exc:
        messages.error(request, str(exc))
        return redirect("classes:detalle", clase_id=clase_id)

    cupo = services.cupo_disponible(clase, fecha=fecha_clase, periodo=periodo) if tipo == Inscripcion.Tipo.CLASE_SUELTA else services.cupo_disponible(clase, periodo=periodo)
    if cupo > 0 and not (
        tipo == Inscripcion.Tipo.CLASE_SUELTA and requiere_precola_suelta(periodo)
    ):
        return _ir_a_pantalla_pago(request, clase_id)

    try:
        _, resultado = services.reservar_clase(
            request.user,
            clase_id,
            periodo=periodo,
            tipo=tipo,
            fecha_clase=fecha_clase,
        )
    except InscripcionDuplicada as exc:
        redirect_resp = _manejar_inscripcion_duplicada(request, exc, clase_id)
        if redirect_resp is not None:
            return redirect_resp
        return redirect("classes:detalle", clase_id=clase_id)
    except services.ReservaError as exc:
        messages.error(request, str(exc))
        return redirect("classes:detalle", clase_id=clase_id)

    messages.success(request, "Te anotamos en la lista de espera.")
    return redirect("classes:detalle", clase_id=clase_id)


@login_required
def inscribir_clase_view(request, clase_id):
    if request.method != "POST":
        return redirect("classes:detalle", clase_id=clase_id)
    return _reservar_desde_detalle(request, clase_id)


@login_required
def anotar_espera_view(request, clase_id):
    if request.method != "POST":
        return redirect("classes:detalle", clase_id=clase_id)

    # El cupo se verificará internamente en `_reservar_desde_detalle` y `reservar_clase`.
    return _reservar_desde_detalle(request, clase_id)


@login_required
def abandonar_espera_view(request, inscripcion_id):
    if request.method != "POST":
        return redirect("classes:mis_reservas")

    inscripcion = get_object_or_404(
        Inscripcion,
        id=inscripcion_id,
        usuario=request.user,
        estado=Inscripcion.Estado.ESPERA,
    )
    clase_id = inscripcion.clase_id
    try:
        services.cancelar_reserva(inscripcion_id, request.user)
        messages.success(request, "Te eliminamos de la lista de espera.")
    except services.ReservaError as exc:
        messages.error(request, str(exc))
    return redirect("classes:detalle", clase_id=clase_id)


@login_required
def mis_reservas(request):
    from apps.payments.inscripcion_pago import (
        filtro_inscripciones_en_reservas,
        precio_clase_periodo,
        resumen_pago_inscripcion,
    )

    inscripciones = (
        Inscripcion.objects.filter(usuario=request.user)
        .filter(filtro_inscripciones_en_reservas())
        .select_related("clase", "clase__profesor", "clase__disciplina", "clase__sala")
        .prefetch_related("ocurrencias")
        .order_by("-fecha_inscripcion")
    )

    from apps.classes.confirmaciones import (
        acciones_anular_inscripcion_impaga,
        mensaje_confirm_cancelar_reserva_suelta,
        mensaje_confirm_salir_lista_espera,
    )
    from apps.classes.ocurrencias import ocurrencias_reserva_ui

    reservas_ui = []
    for i in inscripciones:
        ocurrencias = ocurrencias_reserva_ui(i, desde_fecha=timezone.localdate())

        unitario = precio_clase_periodo(i.clase, i.periodo)
        reservas_ui.append(
            {
                "inscripcion": i,
                "pago": resumen_pago_inscripcion(i),
                "tipo_label": (
                    "Mensualidad"
                    if i.tipo == Inscripcion.Tipo.MENSUAL
                    else "Clase individual"
                ),
                "es_mensual": i.tipo == Inscripcion.Tipo.MENSUAL,
                "precio_unitario": unitario,
                "ocurrencias": ocurrencias,
                "confirm_salir_espera": (
                    mensaje_confirm_salir_lista_espera(i)
                    if i.estado == Inscripcion.Estado.ESPERA
                    else None
                ),
                "anular_inscripcion": (
                    acciones_anular_inscripcion_impaga(i)
                    if i.estado == Inscripcion.Estado.PENDIENTE_PAGO
                    else None
                ),
                "confirm_cancelar_reserva": (
                    mensaje_confirm_cancelar_reserva_suelta(i)
                    if i.tipo != Inscripcion.Tipo.MENSUAL
                    and i.estado == Inscripcion.Estado.RESERVADA
                    else None
                ),
            }
        )

    return render(
        request,
        "classes/mis_reservas.html",
        {
            "reservas_ui": reservas_ui,
            "flow_title": "Mis reservas",
            "flow_subtitle": "Consulta el estado de tus reservas y el detalle de tus clases agendadas.",
            "page_actions_template": "partials/classes/cliente/_mis_reservas_actions.html",
        },
    )


@login_required
def cancelar_reserva_view(request, inscripcion_id):
    if request.method != "POST":
        return redirect("classes:mis_reservas")

    inscripcion = get_object_or_404(
        Inscripcion,
        id=inscripcion_id,
        usuario=request.user,
    )
    clase_id = inscripcion.clase_id

    try:
        resultado = services.cancelar_reserva(inscripcion_id, request.user)
        messages.success(request, resultado.mensaje)
    except services.ReservaError as e:
        messages.error(request, str(e))

    if request.POST.get("destino") == "detalle":
        return redirect("classes:detalle", clase_id=clase_id)
    return redirect("classes:mis_reservas")


@login_required
def cancelar_ocurrencia_view(request, inscripcion_id):
    if request.method != "POST":
        return redirect("classes:mis_reservas")

    from django.utils.dateparse import parse_datetime

    raw = request.POST.get("fecha_clase")
    if not raw:
        messages.error(request, "Falta la fecha de la clase a cancelar.")
        return redirect("classes:mis_reservas")

    dt = parse_datetime(raw)
    if dt is None:
        messages.error(request, "La fecha de la clase no es válida.")
        return redirect("classes:mis_reservas")
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())

    try:
        resultado = services.cancelar_ocurrencia_mensual(
            inscripcion_id, request.user, dt
        )
        messages.success(request, resultado.mensaje)
    except services.ReservaError as e:
        messages.error(request, str(e))

    return redirect("classes:mis_reservas")
