from django.urls import path
from . import views

app_name = "payments"

urlpatterns = [
    path("manage/", views.staff_pagos, name="manage"),
    path("inscripcion/<int:inscripcion_id>/pagar/", views.pagar_inscripcion, name="pagar"),
    path("pago/<int:pago_id>/success/", views.success, name="success"),
    path("pago/<int:pago_id>/failure/", views.failure, name="failure"),
]
