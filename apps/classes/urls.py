from django.urls import path
from . import views

app_name = "classes"

urlpatterns = [
    # Clases (admin)
    path("list/", views.class_list, name="class_list"),
    path("list/rows/", views.class_rows, name="class_rows"),
    path("list/modal/", views.class_modal, name="class_modal"),
    path("list/modal/<int:class_id>/", views.class_modal, name="class_modal_edit"),
    path("list/salas-por-sede/", views.salas_por_sede, name="salas_por_sede"),
    path("list/crear/", views.create_class, name="create_class"),
    path("list/<int:class_id>/editar/", views.update_class, name="update_class"),
    path("list/<int:class_id>/delete/", views.delete_class, name="delete_class"),
    path("list/<int:class_id>/toggle-pause/", views.toggle_class_pause, name="toggle_class_pause"),
    # Ubicaciones (sedes/salas)
    path("locations/", views.locations_list, name="locations_list"),
    path("locations/salas/rows/", views.sala_rows, name="sala_rows"),
    path("locations/sedes/modal/", views.sede_modal, name="sede_modal"),
    path("locations/sedes/modal/<int:sede_id>/", views.sede_modal, name="sede_modal_edit"),
    path("locations/salas/modal/", views.sala_modal, name="sala_modal"),
    path("locations/salas/modal/<int:sala_id>/", views.sala_modal, name="sala_modal_edit"),
    path("locations/sedes/crear/", views.create_sede, name="create_sede"),
    path("locations/sedes/<int:sede_id>/editar/", views.update_sede, name="update_sede"),
    path("locations/salas/crear/", views.create_sala, name="create_sala"),
    path("locations/salas/<int:sala_id>/editar/", views.update_sala, name="update_sala"),
    path("locations/sedes/<int:sede_id>/delete/", views.delete_sede, name="delete_sede"),
    path("locations/salas/<int:sala_id>/delete/", views.delete_sala, name="delete_sala"),
    # Catálogo (disciplinas/profesores)
    path("catalog/", views.catalog, name="catalog"),
    path("catalog/disciplinas/rows/", views.disciplina_rows, name="disciplina_rows"),
    path("catalog/disciplinas/modal/", views.disciplina_modal, name="disciplina_modal"),
    path(
        "catalog/disciplinas/modal/<int:disciplina_id>/",
        views.disciplina_modal,
        name="disciplina_modal_edit",
    ),
    path("catalog/teachers/rows/", views.teacher_rows, name="teacher_rows"),
    path("catalog/teachers/modal/", views.teacher_modal, name="teacher_modal"),
    path(
        "catalog/teachers/modal/<int:teacher_id>/",
        views.teacher_modal,
        name="teacher_modal_edit",
    ),
    path("catalog/disciplinas/crear/", views.create_disciplina, name="create_disciplina"),
    path(
        "catalog/disciplinas/<int:disciplina_id>/editar/",
        views.update_disciplina,
        name="update_disciplina",
    ),
    path("catalog/teachers/crear/", views.create_teacher, name="create_teacher"),
    path(
        "catalog/teachers/<int:teacher_id>/editar/",
        views.update_teacher,
        name="update_teacher",
    ),
    path(
        "catalog/disciplinas/<int:disciplina_id>/delete/",
        views.delete_disciplina,
        name="delete_disciplina",
    ),
    path(
        "catalog/teachers/<int:teacher_id>/delete/",
        views.delete_teacher,
        name="delete_teacher",
    ),
    # Cliente: reservas
    path("browse/", views.browse_clases, name="browse"),
    path("<int:clase_id>/reservar/", views.reservar_clase_view, name="reservar"),
    path("mis-reservas/", views.mis_reservas, name="mis_reservas"),
    path(
        "inscripciones/<int:inscripcion_id>/cancelar/",
        views.cancelar_reserva_view,
        name="cancelar_reserva",
    ),
]
