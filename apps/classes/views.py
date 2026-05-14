from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required

from .forms import ClassForm, TeacherForm
from .models import Class, Teacher

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


@staff_member_required
def delete_teacher(request, teacher_id):
    if request.method == 'POST':
        try:
            teacher = Teacher.objects.get(id=teacher_id)
            teacher.delete()
        except Teacher.DoesNotExist:
            pass
    return redirect('classes:teacher_list')
