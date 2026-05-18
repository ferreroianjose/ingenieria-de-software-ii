from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from . import services
from .forms import ClassForm, TeacherForm, SedeForm, SalaForm, DisciplinaForm
from .models import Class, Inscripcion, Teacher, Sede, Sala, Disciplina
from .services import proxima_ocurrencia


# ── Infrastructure management (staff) ─────────────────────────────────────────

@staff_member_required
def infrastructure_list(request):
    """Vista unificada que muestra Sedes, Salas, Disciplinas y Profesores"""

    # Inicializar formularios y modales
    sede_form = SedeForm()
    sala_form = SalaForm()
    disciplina_form = DisciplinaForm()
    teacher_form = TeacherForm()

    show_sede_modal = False
    show_sala_modal = False
    show_disciplina_modal = False
    show_teacher_modal = False

    # Procesar POST para Sede
    if request.method == 'POST' and 'form_type' in request.POST:
        form_type = request.POST.get('form_type')

        if form_type == 'sede':
            sede_form = SedeForm(request.POST)
            if sede_form.is_valid():
                sede_form.save()
                return redirect('classes:infrastructure_list')
            show_sede_modal = True

        elif form_type == 'sala':
            sala_form = SalaForm(request.POST)
            if sala_form.is_valid():
                sala_form.save()
                return redirect('classes:infrastructure_list')
            show_sala_modal = True

        elif form_type == 'disciplina':
            disciplina_form = DisciplinaForm(request.POST)
            if disciplina_form.is_valid():
                disciplina_form.save()
                return redirect('classes:infrastructure_list')
            show_disciplina_modal = True

        elif form_type == 'teacher':
            teacher_form = TeacherForm(request.POST)
            if teacher_form.is_valid():
                teacher_form.save()
                return redirect('classes:infrastructure_list')
            show_teacher_modal = True

    # Obtener datos optimizados
    sedes = Sede.objects.all().order_by('nombre')
    salas = Sala.objects.select_related('sede').all().order_by('nombre')
    disciplinas = Disciplina.objects.all().order_by('nombre')
    teachers = Teacher.objects.all().order_by('nombre', 'apellido')

    context = {
        'sedes': sedes,
        'salas': salas,
        'disciplinas': disciplinas,
        'teachers': teachers,
        'sede_form': sede_form,
        'sala_form': sala_form,
        'disciplina_form': disciplina_form,
        'teacher_form': teacher_form,
        'show_sede_modal': show_sede_modal,
        'show_sala_modal': show_sala_modal,
        'show_disciplina_modal': show_disciplina_modal,
        'show_teacher_modal': show_teacher_modal,
    }

    return render(request, 'classes/infrastructure_list.html', context)


@staff_member_required
def delete_sede(request, sede_id):
    """Eliminar una sede"""
    if request.method == 'POST':
        try:
            sede = Sede.objects.get(id=sede_id)
            sede.delete()
        except Sede.DoesNotExist:
            pass
    return redirect('classes:infrastructure_list')


@staff_member_required
def delete_sala(request, sala_id):
    """Eliminar una sala"""
    if request.method == 'POST':
        try:
            sala = Sala.objects.get(id=sala_id)
            sala.delete()
        except Sala.DoesNotExist:
            pass
    return redirect('classes:infrastructure_list')


@staff_member_required
def delete_disciplina(request, disciplina_id):
    """Eliminar una disciplina"""
    if request.method == 'POST':
        try:
            disciplina = Disciplina.objects.get(id=disciplina_id)
            disciplina.delete()
        except Disciplina.DoesNotExist:
            pass
    return redirect('classes:infrastructure_list')


@staff_member_required
def delete_teacher(request, teacher_id):
    if request.method == 'POST':
        try:
            teacher = Teacher.objects.get(id=teacher_id)
            teacher.delete()
        except Teacher.DoesNotExist:
            pass
    return redirect('classes:infrastructure_list')


# ── Class management (staff) ─────────────────────────────────────────────────

@staff_member_required
def class_list(request):
    form = ClassForm()
    show_modal = False

    if request.method == 'POST':
        form = ClassForm(request.POST)
        if form.is_valid():
            new_class = form.save(commit=False)
            new_class.estado = 'disponible'
            new_class.save()
            return redirect('classes:class_list')
        show_modal = True

    classes = Class.objects.all()
    return render(
        request,
        'classes/class_list.html',
        {'classes': classes, 'form': form, 'show_modal': show_modal},
    )


@staff_member_required
def teacher_list(request):
    form = TeacherForm()
    show_modal = False

    if request.method == 'POST':
        form = TeacherForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('classes:teacher_list')
        show_modal = True

    teachers = Teacher.objects.all()
    return render(
        request,
        'classes/teacher_list.html',
        {'teachers': teachers, 'form': form, 'show_modal': show_modal},
    )


# ── Client-facing views ──────────────────────────────────────────────────────

@login_required
def browse_clases(request):
    """Catalog of available classes with capacity and next occurrence info."""
    clases = (
        Class.objects.filter(estado='disponible')
        .select_related('profesor', 'disciplina', 'sala', 'sala__sede')
        .prefetch_related('inscripciones')
    )

    clases_con_info = []
    for clase in clases:
        proximo_inicio = proxima_ocurrencia(clase.inicio)
        activas = clase.inscripciones.filter(
            estado__in=[Inscripcion.ESTADO_RESERVADA, Inscripcion.ESTADO_PENDIENTE_PAGO]
        ).count()
        cupo_restante = max(0, clase.cupo_maximo - activas)
        en_espera = clase.inscripciones.filter(estado=Inscripcion.ESTADO_ESPERA).count()
        mi_inscripcion = (
            clase.inscripciones.filter(usuario=request.user)
            .exclude(estado=Inscripcion.ESTADO_CANCELADA)
            .first()
        )
        clases_con_info.append({
            'clase': clase,
            'proximo_inicio': proximo_inicio,
            'cupo_restante': cupo_restante,
            'en_espera': en_espera,
            'mi_inscripcion': mi_inscripcion,
        })

    return render(request, 'classes/browse.html', {'clases_con_info': clases_con_info})


@login_required
def reservar_clase_view(request, clase_id):
    """POST-only action: reserve a spot or join the waitlist."""
    if request.method != 'POST':
        return redirect('classes:browse')

    try:
        inscripcion, resultado = services.reservar_clase(request.user, clase_id)
        if resultado == 'reservada':
            messages.success(request, "reserva exitosa")
        else:
            messages.info(
                request,
                f"has sido registrado a la lista de espera de la clase "
                f"{inscripcion.clase.disciplina} por falta de cupo",
            )
    except services.TelefonoEmergenciaFaltante:
        messages.error(request, "reserva fallida, actualizar el telefono de emergencia")
    except services.InscripcionDuplicada:
        messages.warning(request, "Ya tenés una inscripción activa en esta clase.")
    except services.ClaseNoDisponible:
        messages.error(request, "La clase no está disponible.")
    except Class.DoesNotExist:
        messages.error(request, "La clase no existe.")

    return redirect('classes:browse')


@login_required
def mis_reservas(request):
    """List the authenticated user's active inscriptions."""
    inscripciones = (
        Inscripcion.objects.filter(usuario=request.user)
        .exclude(estado=Inscripcion.ESTADO_CANCELADA)
        .select_related('clase', 'clase__profesor', 'clase__disciplina', 'clase__sala')
        .order_by('-fecha_inscripcion')
    )

    inscripciones_con_info = [
        {
            'inscripcion': i,
            'proximo_inicio': proxima_ocurrencia(i.clase.inicio),
        }
        for i in inscripciones
    ]

    return render(
        request,
        'classes/mis_reservas.html',
        {'inscripciones_con_info': inscripciones_con_info},
    )


@login_required
def cancelar_reserva_view(request, inscripcion_id):
    """POST-only action: cancel a reservation or leave the waitlist."""
    if request.method != 'POST':
        return redirect('classes:mis_reservas')

    try:
        services.cancelar_reserva(inscripcion_id, request.user)
        messages.success(request, "Tu inscripción fue cancelada correctamente.")
    except services.ReservaError as e:
        messages.error(request, str(e))

    return redirect('classes:mis_reservas')
