# notifications/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("test-notifications/", views.TestNotificationView.as_view(), name="test-notifications"),
    path("<str:task_id>/", views.TaskStatusView.as_view(), name="task-status"),
]
