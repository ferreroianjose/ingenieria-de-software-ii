from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    path('generate-qr/', views.generate_qr, name='generate_qr'),
    path('manage/', views.staff_asistencia, name='manage'),
    path('search/', views.buscar_cliente, name='search'),
    path('detail/', views.detalle_cliente_asistencia, name='detail'),
    path('cargar-telefono/', views.cargar_telefono, name='cargar_telefono'),
    path('register/', views.registrar_asistencia, name='register'),
    path('undo-register/', views.anular_asistencia, name='undo_register'),
    path('pay-cash/', views.cobrar_efectivo_recepcion, name='pay_cash'),
    path('approve-tutor/', views.aprobar_constancia_recepcion, name='approve_tutor'),
    path('undo-approve-tutor/', views.deshacer_constancia_recepcion, name='undo_approve_tutor'),
    path('planilla-grid/', views.planilla_asistencia_grid, name='planilla_grid'),
    path('planilla-grid/print/', views.planilla_asistencia_print, name='planilla_print'),
]
