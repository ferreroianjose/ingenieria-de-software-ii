from django.shortcuts import render
from GYMFlow.access import staff_required

@staff_required
def staff_pagos(request):
    return render(request, "payments/manage.html")

