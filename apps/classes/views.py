from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required

from .forms import ClassForm, TeacherForm, SedeForm, SalaForm, DisciplinaForm
from .models import Class, Teacher, Sede, Sala, Disciplina

# Vista unificada de Infraestructura
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


# Vistas originales (mantener compatibilidad)
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
