from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from .models import Class

@staff_member_required
def class_list(request):
    classes = Class.objects.all()
    return render(request, 'classes/class_list.html', {'classes': classes})
