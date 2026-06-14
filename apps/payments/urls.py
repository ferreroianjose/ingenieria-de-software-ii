from django.urls import path
from . import views

app_name = "payments"

urlpatterns = [
    path("manage/", views.staff_pagos, name="manage"),
    path("mis-pagos/", views.mis_pagos, name="mis_pagos"),
    path(
        "clase/<int:clase_id>/pago/",
        views.seleccion_pago_clase,
        name="seleccion_pago_clase",
    ),
    path(
        "clase/<int:clase_id>/pagar/",
        views.pagar_clase,
        name="pagar_clase",
    ),
    path(
        "inscripcion/<int:inscripcion_id>/pago/",
        views.seleccion_pago,
        name="seleccion_pago",
    ),
    path("inscripcion/<int:inscripcion_id>/pagar/", views.pagar_inscripcion, name="pagar"),
    path("pago/<int:pago_id>/success/", views.success, name="success"),
    path("pago/<int:pago_id>/failure/", views.failure, name="failure"),
    path("webhooks/mercadopago/", views.mercadopago_webhook, name="mercadopago_webhook"),
    path("search-client/", views.buscar_cliente_pago, name="search_client"),
    path("client-detail/", views.detalle_pago_cliente, name="client_detail"),
    path("registrar-pago/<int:inscripcion_id>/", views.registrar_pago_sucursal, name="registrar_pago_sucursal"),
    path("global-history/", views.historial_pagos_global, name="global_history"),
]
