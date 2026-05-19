from django.urls import path
from . import views

app_name = "payments"

urlpatterns = [
    path("manage/", views.staff_pagos, name="manage"),
]
