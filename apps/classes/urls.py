from django.urls import path
from . import views

app_name = 'classes'

urlpatterns = [
    # Staff management
    path('list/', views.class_list, name='class_list'),
    path('teachers/', views.teacher_list, name='teacher_list'),
    path('teachers/<int:teacher_id>/delete/', views.delete_teacher, name='delete_teacher'),
    path('infrastructure/', views.infrastructure_list, name='infrastructure_list'),
    path('infrastructure/sedes/<int:sede_id>/delete/', views.delete_sede, name='delete_sede'),
    path('infrastructure/salas/<int:sala_id>/delete/', views.delete_sala, name='delete_sala'),
    path('infrastructure/disciplinas/<int:disciplina_id>/delete/', views.delete_disciplina, name='delete_disciplina'),

    # Client-facing
    path('browse/', views.browse_clases, name='browse'),
    path('<int:clase_id>/reservar/', views.reservar_clase_view, name='reservar'),
    path('mis-reservas/', views.mis_reservas, name='mis_reservas'),
    path('inscripciones/<int:inscripcion_id>/cancelar/', views.cancelar_reserva_view, name='cancelar_reserva'),
]
