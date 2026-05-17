from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.urls import reverse

from .forms import ClassForm, TeacherForm, SedeForm, SalaForm, DisciplinaForm
from .models import Class, Teacher, Sede, Sala, Disciplina
from .search import apply_text_search
from .htmx import hx_ok


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
        )
    if level == "success":
        messages.success(request, message)
    else:
        messages.error(request, message)
    return redirect(redirect_to)


def _class_rows_refresh():
    return {
        "url": reverse("classes:class_rows"),
        "target": "#class-rows-tbody",
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
        }
    qs = _filter_class_queryset(request)
    return {
        "classes": qs,
        "searched": True,
        "q": request.GET.get("q", ""),
    }


def _all_class_rows_context():
    return {
        "classes": Class.objects.select_related(
            "disciplina", "sala", "sala__sede", "profesor"
        ).order_by("dia_semana", "hora_inicio"),
        "searched": True,
        "q": "",
    }


CLASS_LIST_VIEW_TABS = [
    {"id": "lista", "label": "Listado"},
    {"id": "cronograma", "label": "Cronograma"},
]

CATALOG_VIEW_TABS = [
    {"id": "disciplinas", "label": "Disciplinas"},
    {"id": "profesores", "label": "Profesores"},
]


@staff_member_required
def class_list(request):
    tab = request.GET.get("tab", "lista")
    if tab not in {t["id"] for t in CLASS_LIST_VIEW_TABS}:
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
            "view_tabs": CLASS_LIST_VIEW_TABS,
            "initial_tab": tab,
            "class_rows_searched": False,
        },
    )


@staff_member_required
def class_rows(request):
    return render(
        request,
        "partials/classes/rows/_class_rows.html",
        _class_rows_context(request),
    )


@staff_member_required
def locations_list(request):
    sedes = Sede.objects.all().order_by("nombre")
    selected_sede_id = request.GET.get("sede_id")
    if selected_sede_id:
        try:
            selected_sede_id = int(selected_sede_id)
        except ValueError, TypeError:
            selected_sede_id = sedes[0].id if sedes else None
    elif sedes:
        selected_sede_id = sedes[0].id
    else:
        selected_sede_id = None

    return render(
        request,
        "classes/locations_list.html",
        {
            "sedes": sedes,
            "selected_sede_id": selected_sede_id,
            "sede_form": SedeForm(),
            "sala_form": SalaForm(),
            "create_sede_url": reverse("classes:create_sede"),
            "create_sala_url": reverse("classes:create_sala"),
        },
    )


@staff_member_required
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


@staff_member_required
def catalog(request):
    tab = request.GET.get("tab", "disciplinas")
    if tab not in ("disciplinas", "profesores"):
        tab = "disciplinas"
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
        },
    )


@staff_member_required
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


@staff_member_required
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


@staff_member_required
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


@staff_member_required
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


@staff_member_required
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


@staff_member_required
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


@staff_member_required
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


@staff_member_required
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


@staff_member_required
def create_sede(request):
    if request.method == "POST":
        form = SedeForm(request.POST)
        if form.is_valid():
            sede = form.save()
            return _hx_ok_or_redirect(
                request,
                message=f"La sede «{sede.nombre}» fue creada.",
                redirect_to="classes:locations_list",
                close_modal="sedeModalOpen",
                locations_reload=(
                    reverse("classes:locations_list") + f"?sede_id={sede.pk}"
                ),
            )

        if request.headers.get("HX-Request"):
            return _render_modal(
                request,
                body_template="partials/classes/modals/_sede_modal_body.html",
                form=form,
                title="Agregar sede",
                subtitle="Ingresá los datos de la nueva sede.",
                button_label="Guardar sede",
                action_url=reverse("classes:create_sede"),
                show_var="sedeModalOpen",
                container_id="sede-modal",
            )
    return redirect("classes:locations_list")


@staff_member_required
def create_sala(request):
    if request.method == "POST":
        form = SalaForm(request.POST)
        if form.is_valid():
            sala = form.save()
            sede = sala.sede
            return _hx_ok_or_redirect(
                request,
                message=f"La sala «{sala.nombre}» fue creada.",
                redirect_to="classes:locations_list",
                close_modal="salaModalOpen",
                refresh=_sala_rows_refresh(sede.pk),
            )

        if request.headers.get("HX-Request"):
            return _render_modal(
                request,
                body_template="partials/classes/modals/_sala_modal_body.html",
                form=form,
                title="Agregar sala",
                subtitle="Ingresá los datos de la nueva sala.",
                button_label="Guardar sala",
                action_url=reverse("classes:create_sala"),
                show_var="salaModalOpen",
                container_id="sala-modal",
                lock_sede=True,
                selected_sede_id=request.POST.get("sede"),
            )
    return redirect("classes:locations_list")


@staff_member_required
def disciplina_modal(request, disciplina_id=None):
    if disciplina_id is not None:
        instance = get_object_or_404(Disciplina, pk=disciplina_id)
        form = DisciplinaForm(instance=instance)
    else:
        instance = None
        form = DisciplinaForm()
    return _render_disciplina_modal_panel(request, form, instance)


@staff_member_required
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


@staff_member_required
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


@staff_member_required
def teacher_modal(request, teacher_id=None):
    if teacher_id is not None:
        instance = get_object_or_404(Teacher, pk=teacher_id)
        form = TeacherForm(instance=instance)
    else:
        instance = None
        form = TeacherForm()
    return _render_teacher_modal_panel(request, form, instance)


@staff_member_required
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


@staff_member_required
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


@staff_member_required
def delete_sede(request, sede_id):
    if request.method != "POST":
        return redirect("classes:locations_list")
    sede = get_object_or_404(Sede, pk=sede_id)
    try:
        nombre = sede.nombre
        sede.delete()
        return _hx_ok_or_redirect(
            request,
            message=f"La sede «{nombre}» fue eliminada.",
            redirect_to="classes:locations_list",
            locations_reload=reverse("classes:locations_list"),
        )
    except ProtectedError:
        return _hx_ok_or_redirect(
            request,
            message=f"No se puede eliminar la sede «{sede.nombre}» porque tiene salas con clases asignadas.",
            redirect_to="classes:locations_list",
            level="error",
        )


@staff_member_required
def delete_sala(request, sala_id):
    if request.method != "POST":
        return redirect("classes:locations_list")
    sala = get_object_or_404(Sala, pk=sala_id)
    sede_id = sala.sede_id
    try:
        nombre = sala.nombre
        sala.delete()
        return _hx_ok_or_redirect(
            request,
            message=f"La sala «{nombre}» fue eliminada.",
            redirect_to="classes:locations_list",
            refresh=_sala_rows_refresh(sede_id),
        )
    except ProtectedError:
        return _hx_ok_or_redirect(
            request,
            message=f"No se puede eliminar la sala «{sala.nombre}» porque tiene clases asignadas.",
            redirect_to="classes:locations_list",
            level="error",
        )


@staff_member_required
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


@staff_member_required
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
