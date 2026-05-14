from django.shortcuts import render, redirect
from django.contrib.admin.views.decorators import staff_member_required

from .forms import ClassForm
from .models import Class

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
