from django.urls import path
from . import views

app_name = 'classes'

urlpatterns = [
    path('list/', views.class_list, name='class_list'),
    path('teachers/', views.teacher_list, name='teacher_list'),
    path('teachers/<int:teacher_id>/delete/', views.delete_teacher, name='delete_teacher'),
]